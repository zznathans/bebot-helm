<?php
/*
* Market.php - Richer GMI market overview: search, live orders, price history and item links.
*
* Custom module for BeBot (https://github.com/J-Soft/BeBot), dropped into Custom/Modules/
* so it loads alongside the stock Modules/Ao/Gmi.php without modifying it.
*
* Data source: the public GMI API documented at https://gmi.nadybot.org/ (same API Gmi.php uses).
* That API is live-orders-only, so price history is built locally by polling watched items on a timer.
*/

$market_core = new Market($bot);

class Market extends BaseActiveModule
{
	function __construct(&$bot)
	{
		parent::__construct($bot, get_class($this));
		// Per-subcommand access levels (matching the second word of the message, e.g. "market
		// watch" -> "watch") - an admin can retune any of these independently at runtime via
		// "commands update all market <subcommand> <LEVEL>", no code change needed. Only reaches
		// this granularity though: it can't tell "market help settings" apart from "market help
		// search" (both are subcommand "help") - that finer split is an inline check in
		// help_settings() instead. Free-text searches/AOIDs (arbitrary second words) fall through
		// to the command's own GUEST default below, not any of these entries.
		$this->register_command("all", "market", "GUEST", array(
			"register" => "GUEST",
			"unregister" => "GUEST",
			"watch" => "GUEST",
			"unwatch" => "GUEST",
			"status" => "GUEST",
			"watchlist" => "GUEST",
			"help" => "GUEST",
			"user" => "GUEST"
		));
		$this->register_alias("market", "mkt");
		$this->help['description'] = "Market overview: search for an item and see a summary, price history and live orders.";
		$this->help['command']['market <item name>'] = "Search for an item by (partial) name";
		$this->help['command']['market <aoid>'] = "Show the full market overview for a specific item ID";
		$this->help['command']['market status'] = "Show an overview of market tracking (settings, item counts) without listing every item";
		$this->help['command']['market status details'] = "Show every item currently tracked, its source (auto/manual) and last-updated time";
		$this->help['command']['market watch <item>'] = "Get a tell when a new order is posted for an item (requires !market register first)";
		$this->help['command']['market unwatch <aoid>'] = "Stop watching an item";
		$this->help['command']['market watchlist'] = "List everything on your personal watchlist";
		$this->help['command']['market user stats'] = "Show your own Market usage stats (ADMIN+ can pass a player name to check anyone)";
		$this->help['command']['market help'] = "Show the Market module's in-game help pages";
		$this->help['command']['market register'] = "Opt into Market notifications and set up your own watchlist";
		$this->help['command']['market unregister'] = "Erase your registration, watchlist, queued notifications, and usage stats (irreversible, requires confirmation)";

		$this->bot->core("settings")
			->create("Market", "Enabled", false, "Should the Market module respond to commands and track prices at all ?", "On;Off");
		$this->bot->core("settings")
			->create("Market", "ApiUrl", "https://gmi.nadybot.org", "What's the GMI search API URL we should use (Nadybot's by default) ?");
		$this->bot->core("settings")
			->create("Market", "PollIntervalMinutes", 30, "How often (in minutes) should watched items be re-polled to build price history ?");
		$this->bot->core("settings")
			->create("Market", "HistoryRetentionDays", 90, "How many days of price history should be kept per item ?");
		$this->bot->core("settings")
			->create("Market", "WatchExpireDays", 30, "Stop polling an item if nobody has looked it up again within this many days");
		$this->bot->core("settings")
			->create("Market", "PollBatchSize", 25, "Maximum number of watched items to re-poll per timer cycle");
		$this->bot->core("settings")
			->create("Market", "AutoTrackEnabled", true, "Should the bot automatically track price history for the most actively-traded items (sourced from ao-stonks.com) ?", "On;Off");
		$this->bot->core("settings")
			->create("Market", "AutoTrackCount", 100, "How many of the most actively-traded items should be auto-tracked ?");
		$this->bot->core("settings")
			->create("Market", "AutoTrackIntervalMinutes", 60, "How often (in minutes) should the auto-tracked item list be resynced from ao-stonks.com ?");
		$this->bot->core("settings")
			->create("Market", "AutoTrackSourceUrl", "https://ao-stonks.com", "What site should be used to determine the most actively-traded items ?");
		$this->bot->core("settings")
			->create("Market", "AutoTrackLastSync", 0, "Internal: unix timestamp of the last successful auto-track resync - do not set manually");
		$this->bot->core("settings")
			->create("Market", "MaxSubscriptionsPerPlayer", 25, "Maximum number of items a single player can watch at once");
		$this->bot->core("settings")
			->create("Market", "LogToPrivateChannel", false, "Should Market activity (searches, watches, registrations, etc.) be broadcast to the bot's private channel ?", "On;Off");

		$this->table();

		// Deliver any pending watchlist alerts once a subscriber logs back on - see notify() below.
		$this->bot->core("logon_notifies")->register($this);

		$this->bot->core("timer")->register_callback("Market", $this);
		$existing = $this->bot->core("timer")->list_timed_events("Market");
		$scheduled = array();
		foreach ($existing as $timer) {
			$scheduled[] = $timer['name'];
		}
		if (!in_array("Market-Poll", $scheduled)) {
			$interval = 60 * intval($this->bot->core("settings")->get("Market", "PollIntervalMinutes"));
			if ($interval < 60) {
				$interval = 60;
			}
			$this->bot->core("timer")->add_timer(true, "Market", $interval, "Market-Poll", "internal", $interval, "None");
		}
		if (!in_array("Market-AutoTrack", $scheduled)) {
			$autoInterval = 60 * intval($this->bot->core("settings")->get("Market", "AutoTrackIntervalMinutes"));
			if ($autoInterval < 60) {
				$autoInterval = 60;
			}
			$this->bot->core("timer")->add_timer(true, "Market", $autoInterval, "Market-AutoTrack", "internal", $autoInterval, "None");
		}

		// Catch up immediately on startup if the auto-tracked list is staler than the configured
		// resync interval (e.g. the bot was down/redeployed past when the timer would have fired),
		// rather than waiting for the next scheduled tick.
		if ($this->bot->core("settings")->get("Market", "Enabled") && $this->bot->core("settings")->get("Market", "AutoTrackEnabled")) {
			$autoIntervalSeconds = 60 * intval($this->bot->core("settings")->get("Market", "AutoTrackIntervalMinutes"));
			$lastSync = intval($this->bot->core("settings")->get("Market", "AutoTrackLastSync"));
			if ((time() - $lastSync) >= $autoIntervalSeconds) {
				$this->sync_top_traded_items();
			}
		}
	}

	function table()
	{
		$this->bot->db->query(
			"CREATE TABLE IF NOT EXISTS " . $this->bot->db->define_tablename("market_watch", "false") . "
				(aoid INT NOT NULL PRIMARY KEY,
					name VARCHAR(150) NOT NULL,
					ql INT NOT NULL DEFAULT 0,
					icon INT NOT NULL DEFAULT 0,
					first_seen INT NOT NULL,
					last_polled INT NOT NULL DEFAULT 0)"
		);
		$this->bot->db->query(
			"CREATE TABLE IF NOT EXISTS " . $this->bot->db->define_tablename("market_history", "false") . "
				(id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
					aoid INT NOT NULL,
					ts INT NOT NULL,
					sell_count INT NOT NULL DEFAULT 0,
					buy_count INT NOT NULL DEFAULT 0,
					min_sell_price BIGINT NOT NULL DEFAULT 0,
					max_buy_price BIGINT NOT NULL DEFAULT 0,
					avg_sell_price BIGINT NOT NULL DEFAULT 0,
					avg_buy_price BIGINT NOT NULL DEFAULT 0,
					INDEX market_history_aoid_ts (aoid, ts))"
		);
		if (!$this->bot->db->get_version("market_watch")) {
			$this->bot->db->set_version("market_watch", 1);
		}
		if (!$this->bot->db->get_version("market_history")) {
			$this->bot->db->set_version("market_history", 1);
		}
		if ($this->bot->db->get_version("market_watch") < 2) {
			$this->bot->db->update_table(
				"market_watch",
				"auto_tracked",
				"add",
				"ALTER TABLE #___market_watch ADD COLUMN auto_tracked TINYINT NOT NULL DEFAULT 0"
			);
			$this->bot->db->set_version("market_watch", 2);
		}
		if ($this->bot->db->get_version("market_history") < 2) {
			// avg_sell_price/avg_buy_price are anchored to the item's own QL from here on (a single
			// AOID's live orders can span very different QLs, so a blended average across all of them
			// is meaningless) - these counts record how many orders actually matched that QL each
			// cycle, so history_average() can exclude snapshots with zero matches instead of letting
			// them drag the trend toward 0.
			$this->bot->db->update_table(
				"market_history",
				"anchor_sell_count",
				"add",
				"ALTER TABLE #___market_history ADD COLUMN anchor_sell_count INT NOT NULL DEFAULT 0"
			);
			$this->bot->db->update_table(
				"market_history",
				"anchor_buy_count",
				"add",
				"ALTER TABLE #___market_history ADD COLUMN anchor_buy_count INT NOT NULL DEFAULT 0"
			);
			$this->bot->db->set_version("market_history", 2);
		}

		// Per-player watchlist: which items a registered player wants order-alert tells for. side/
		// min_price/max_price/min_volume are reserved for a later iteration's alert criteria - until
		// that ships they stay at their permissive defaults and every new order notifies regardless.
		$this->bot->db->query(
			"CREATE TABLE IF NOT EXISTS " . $this->bot->db->define_tablename("market_subscriptions", "false") . "
				(id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
					player VARCHAR(30) NOT NULL,
					aoid INT NOT NULL,
					side ENUM('any', 'buy', 'sell') NOT NULL DEFAULT 'any',
					min_price BIGINT NULL,
					max_price BIGINT NULL,
					min_volume INT NULL,
					created_at INT NOT NULL,
					UNIQUE INDEX market_subscriptions_player_aoid (player, aoid))"
		);
		// The "have we already alerted on this exact order" ledger - rebuilt every poll cycle in
		// detect_new_orders(), so it never needs a separate pruning job.
		$this->bot->db->query(
			"CREATE TABLE IF NOT EXISTS " . $this->bot->db->define_tablename("market_seen_orders", "false") . "
				(aoid INT NOT NULL,
					fingerprint VARCHAR(64) NOT NULL,
					PRIMARY KEY (aoid, fingerprint))"
		);
		// Queued tells for subscribers who were offline when a new order was detected - drained by
		// notify() (the logon_notifies callback) once they next log on.
		$this->bot->db->query(
			"CREATE TABLE IF NOT EXISTS " . $this->bot->db->define_tablename("market_pending_alerts", "false") . "
				(id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
					player VARCHAR(30) NOT NULL,
					aoid INT NOT NULL,
					message VARCHAR(500) NOT NULL,
					created_at INT NOT NULL)"
		);
		// Per-player action ledger backing !market user stats.
		$this->bot->db->query(
			"CREATE TABLE IF NOT EXISTS " . $this->bot->db->define_tablename("market_user_actions", "false") . "
				(id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
					player VARCHAR(30) NOT NULL,
					action VARCHAR(20) NOT NULL,
					aoid INT NULL,
					created_at INT NOT NULL,
					INDEX market_user_actions_player_ts (player, created_at))"
		);
		// Market's own self-service user list - independent of Core/User.php's #___users (which is
		// admin-gated via !adduser). Registering here is what !market watch actually requires; there's
		// deliberately no dependency on the bot's core user table at all.
		$this->bot->db->query(
			"CREATE TABLE IF NOT EXISTS " . $this->bot->db->define_tablename("market_users", "false") . "
				(player VARCHAR(30) NOT NULL PRIMARY KEY,
					registered_at INT NOT NULL)"
		);
		if (!$this->bot->db->get_version("market_subscriptions")) {
			$this->bot->db->set_version("market_subscriptions", 1);
		}
		if (!$this->bot->db->get_version("market_seen_orders")) {
			$this->bot->db->set_version("market_seen_orders", 1);
		}
		if (!$this->bot->db->get_version("market_pending_alerts")) {
			$this->bot->db->set_version("market_pending_alerts", 1);
		}
		if ($this->bot->db->get_version("market_pending_alerts") < 2) {
			// notify_subscribers() now wraps its message in make_blob() (a bare chatcmd() link
			// doesn't render as clickable sent directly as a tell) - the header/chrome that wraps
			// adds enough overhead to exceed the original VARCHAR(500).
			$this->bot->db->update_table(
				"market_pending_alerts",
				"message",
				"modify",
				"ALTER TABLE #___market_pending_alerts MODIFY COLUMN message TEXT NOT NULL"
			);
			$this->bot->db->set_version("market_pending_alerts", 2);
		}
		if (!$this->bot->db->get_version("market_user_actions")) {
			$this->bot->db->set_version("market_user_actions", 1);
		}
		if (!$this->bot->db->get_version("market_users")) {
			$this->bot->db->set_version("market_users", 1);
		}
	}

	function command_handler($name, $msg, $channel)
	{
		if (!$this->bot->core("settings")->get("Market", "Enabled")) {
			return "The Market module is currently disabled. Ask an admin to turn it on via the bot's settings command (Market.Enabled).";
		}
		if (preg_match('/^(?:market|mkt)\s+register\s*$/i', $msg)) {
			return $this->cmd_register($name);
		} elseif (preg_match('/^(?:market|mkt)\s+unregister(?:\s+(confirm))?\s*$/i', $msg, $info)) {
			return $this->cmd_unregister($name, isset($info[1]) && strtolower($info[1]) === "confirm");
		} elseif (preg_match('/^(?:market|mkt)\s+help\s*(.*)$/i', $msg, $info)) {
			$this->log_action($name, "help");
			return $this->show_help($name, trim($info[1]));
		} elseif (preg_match('/^(?:market|mkt)\s+status\s+details\s*$/i', $msg)) {
			$this->log_action($name, "status details");
			return $this->show_status_details();
		} elseif (preg_match('/^(?:market|mkt)\s+status\s*$/i', $msg)) {
			$this->log_action($name, "status");
			return $this->show_status();
		} elseif (preg_match('/^(?:market|mkt)\s+watchlist\s*$/i', $msg)) {
			$this->log_action($name, "watchlist");
			return $this->show_watchlist($name);
		} elseif (preg_match('/^(?:market|mkt)\s+user\s+stats\s*(.*)$/i', $msg, $info)) {
			$target = trim($info[1]);
			$this->log_action($name, "userstats");
			return $this->show_user_stats($name, $target === "" ? null : $target);
		} elseif (preg_match('/^(?:market|mkt)\s+unwatch\s+([0-9]+)\s*$/i', $msg, $info)) {
			return $this->cmd_unwatch($name, intval($info[1]));
		} elseif (preg_match('/^(?:market|mkt)\s+watch\s+([0-9]+)\s*$/i', $msg, $info)) {
			return $this->cmd_watch($name, intval($info[1]));
		} elseif (preg_match('/^(?:market|mkt)\s+watch\s+(.+)$/i', $msg, $info)) {
			$this->log_action($name, "search");
			return $this->search_items(trim($info[1]), "market watch", "Watch");
		} elseif (preg_match('/^(?:market|mkt)\s+([0-9]+)\s*$/i', $msg, $info)) {
			$this->log_action($name, "overview", intval($info[1]));
			return $this->show_overview($name, intval($info[1]));
		} elseif (preg_match('/^(?:market|mkt)\s+(.+)$/i', $msg, $info)) {
			$this->log_action($name, "search");
			return $this->search_items(trim($info[1]));
		} else {
			return "Usage: market <item name>  or  market <aoid>  or  market status  or  market status details  or  market register  or  market watch <item>  or  market unwatch <aoid>  or  market watchlist  or  market user stats  or  market help";
		}
	}

	/*
	Market's own registration (market_users), not Core/User.php's #___users - see cmd_register()
	below and the table() comment on market_users for why these are kept independent.
	*/
	function is_registered($name)
	{
		$result = $this->bot->db->select(
			"SELECT 1 FROM #___market_users WHERE player = '" . $this->bot->db->real_escape_string($name) . "'"
		);
		return !empty($result);
	}

	/*
	Self-service opt-in: anyone (GUEST) can register, no admin action required. Also flips the
	shared notify flag (Main/15_Notify.php) so the bot tracks their online status for immediate
	tell delivery - see notify_subscribers()/notify() - and sends back an info blob explaining the
	service, same as every other Market reply.
	*/
	function cmd_register($name)
	{
		if ($this->is_registered($name)) {
			return "You're already registered. Try " . $this->bot->core("tools")->chatcmd("market help watch", "market help watch") . " for how to build a watchlist.";
		}

		$nameEsc = $this->bot->db->real_escape_string($name);
		$this->bot->db->query(
			"INSERT INTO #___market_users (player, registered_at) VALUES ('" . $nameEsc . "', " . time() . ")"
		);
		$this->bot->core("notify")->add($name, $name);
		$this->log_action($name, "register");

		$tools = $this->bot->core("tools");
		$limit = $this->bot->core("settings")->get("Market", "MaxSubscriptionsPerPlayer");
		$out = "You're registered with the Market module.\n\n";
		$out .= "This lets you build a personal watchlist - " . $tools->chatcmd("market watch <item>", "market watch <item>")
			. " adds an item, and you'll get a tell as soon as a new order is posted for it (immediately if you're\n";
		$out .= "online, or the next time you log on if you weren't). Capped at " . $limit . " item(s) at once; "
			. $tools->chatcmd("market unwatch <aoid>", "market unwatch <aoid>") . " removes one, and "
			. $tools->chatcmd("market watchlist", "market watchlist") . " lists what you're currently watching.\n\n";
		$out .= "If you ever want out: " . $tools->chatcmd("market unregister", "market unregister")
			. " erases your registration, your whole watchlist, any notifications waiting for you, and your usage stats -\n";
		$out .= "it doesn't touch item price history, which isn't tied to any one player. It's irreversible, so it asks you to confirm first.\n";
		return $tools->make_blob("Welcome to Market", $out);
	}

	/*
	Erases everything this player opted into (registration, watchlist, queued tells, and their
	usage-stats ledger in market_user_actions) plus turns off the shared notify flag. Destructive
	and irreversible, so it's gated behind an explicit confirm step - see the make_blob() warning
	panel below, same click-to-confirm pattern as AltsUi::add_alt()/confirm(). Never touches any
	item-level price history/tracking, which isn't player-specific to begin with.
	*/
	function cmd_unregister($name, $confirmed = false)
	{
		if (!$this->is_registered($name)) {
			return "You're not registered, so there's nothing to erase.";
		}

		$tools = $this->bot->core("tools");

		if (!$confirmed) {
			$inside = "##highlight##This cannot be undone.##end## Confirming will permanently erase your Market ";
			$inside .= "registration, your entire watchlist, any notifications waiting for you, and all of your ";
			$inside .= "recorded usage stats (market user stats).\n\n";
			$inside .= $tools->chatcmd("market unregister confirm", "Confirm - erase everything");
			return $tools->make_blob("Unregister from Market - Are you sure?", $inside);
		}

		$nameEsc = $this->bot->db->real_escape_string($name);
		$subCount = $this->bot->db->select("SELECT COUNT(*) FROM #___market_subscriptions WHERE player = '" . $nameEsc . "'");
		$watchCount = !empty($subCount) ? (int) $subCount[0][0] : 0;

		$this->bot->db->query("DELETE FROM #___market_subscriptions WHERE player = '" . $nameEsc . "'");
		$this->bot->db->query("DELETE FROM #___market_pending_alerts WHERE player = '" . $nameEsc . "'");
		$this->bot->db->query("DELETE FROM #___market_users WHERE player = '" . $nameEsc . "'");
		$this->bot->db->query("DELETE FROM #___market_user_actions WHERE player = '" . $nameEsc . "'");
		$this->bot->core("notify")->del($name);
		$this->announce($name, "unregister");

		return "Unregistered. Removed " . $watchCount . " watchlist item(s), any pending notifications, and all of your usage stats.";
	}

	function log_action($player, $action, $aoid = null)
	{
		$playerEsc = $this->bot->db->real_escape_string($player);
		$actionEsc = $this->bot->db->real_escape_string($action);
		$aoidSql = ($aoid === null) ? "NULL" : intval($aoid);
		$this->bot->db->query(
			"INSERT INTO #___market_user_actions (player, action, aoid, created_at) VALUES ('"
				. $playerEsc . "', '" . $actionEsc . "', " . $aoidSql . ", " . time() . ")"
		);
		$this->announce($player, $action, $aoid);
	}

	/*
	Broadcasts a Market activity line to the bot's private channel, gated by
	Market.LogToPrivateChannel (off by default) - same opt-in pattern as Relay.Logoninpgroup
	in Modules/Logon.php::show_logon(). Called from log_action() so every action tracked there
	is covered automatically, plus directly from cmd_unregister() which bypasses log_action()
	since it wipes its own ledger.
	*/
	function announce($player, $action, $aoid = null)
	{
		if (!$this->bot->core("settings")->get("Market", "LogToPrivateChannel")) {
			return;
		}
		$label = str_replace("_", " ", $action);
		$suffix = "";
		if ($aoid !== null) {
			$item = $this->bot->db->select("SELECT name FROM aorefs WHERE id = " . intval($aoid) . " LIMIT 1");
			$suffix = !empty($item) ? (" (" . $item[0][0] . ")") : (" (AOID " . $aoid . ")");
		}
		$this->bot->send_pgroup($player . " used market " . $label . $suffix);
	}

	/*
	!market help [topic] - a landing page linking out to one blob per topic, same
	menu-of-linked-blobs pattern Modules/AccessControlUi.php uses for its `commands` command.
	*/
	function show_help($name, $topic = "")
	{
		switch (strtolower($topic)) {
			case "register":
			case "registering":
				return $this->help_register();
			case "search":
			case "overview":
				return $this->help_search();
			case "watch":
			case "watchlist":
			case "alerts":
				return $this->help_watch();
			case "status":
			case "tracking":
				return $this->help_status();
			case "stats":
			case "user":
				return $this->help_stats();
			case "settings":
			case "admin":
				return $this->help_settings($name);
			default:
				return $this->help_landing($name);
		}
	}

	function help_landing($name)
	{
		$tools = $this->bot->core("tools");
		$out = "Search GMI prices, track history, build a personal watchlist, and get alerted when new orders show up.\n\n";
		$out .= "[" . $tools->chatcmd("market help register", "Registering") . "] - opt in/out of Market notifications\n";
		$out .= "[" . $tools->chatcmd("market help search", "Searching & Item Overview") . "] - find items and read their price/QL breakdown\n";
		$out .= "[" . $tools->chatcmd("market help watch", "Watchlist & Alerts") . "] - get a tell when a new order is posted\n";
		$out .= "[" . $tools->chatcmd("market help status", "Tracking Status") . "] - see everything currently being tracked\n";
		$out .= "[" . $tools->chatcmd("market help stats", "Your Stats") . "] - your own usage history\n";
		if ($this->bot->core("security")->check_access($name, "ADMIN")) {
			$out .= "[" . $tools->chatcmd("market help settings", "Settings") . "] - every bot setting this module exposes\n";
		}
		return $tools->make_blob("Market Help", $out);
	}

	function help_search()
	{
		$tools = $this->bot->core("tools");
		$out = "__________Searching & Item Overview_________\n\n";
		$out .= "market <item name>\n";
		$out .= "  Search the local item database by (partial) name. Click a result to open its full overview.\n";
		$out .= "  Example: " . $tools->chatcmd("market viralbots", "market viralbots") . "\n\n";
		$out .= "market <aoid>\n";
		$out .= "  Full overview for a specific item ID: icon/item-info links, a live buy/sell summary,\n";
		$out .= "  a price-by-QL-band breakdown (one item ID can have orders across very different\n";
		$out .= "  qualities, so a single blended average wouldn't mean much), and the cheapest sell /\n";
		$out .= "  highest buy orders right now.\n\n";
		$out .= "Looking up an item also starts tracking its price history automatically - that's\n";
		$out .= "separate from getting alerted about it, see " . $tools->chatcmd("market help watch", "Watchlist & Alerts") . ".\n\n";
		$out .= "[" . $tools->chatcmd("market help", "Back to Market Help") . "]";
		return $tools->make_blob("Market Help: Searching & Overview", $out);
	}

	function help_register()
	{
		$tools = $this->bot->core("tools");
		$out = "__________Registering_________\n\n";
		$out .= "market register\n";
		$out .= "  Opt into Market notifications - anyone can run this, no admin action needed. Sends you\n";
		$out .= "  an info window and lets the bot know to track your online status, so watchlist alerts\n";
		$out .= "  can reach you immediately when you're online.\n\n";
		$out .= "market unregister\n";
		$out .= "  Erases your registration, your entire watchlist, and any notifications waiting for you.\n";
		$out .= "  Doesn't affect item price history (that's not tied to any one player) or your\n";
		$out .= "  " . $tools->chatcmd("market help stats", "usage stats") . ", which are a separate thing.\n\n";
		$out .= "[" . $tools->chatcmd("market help", "Back to Market Help") . "]";
		return $tools->make_blob("Market Help: Registering", $out);
	}

	function help_watch()
	{
		$tools = $this->bot->core("tools");
		$limit = $this->bot->core("settings")->get("Market", "MaxSubscriptionsPerPlayer");
		$out = "__________Watchlist & Alerts_________\n\n";
		$out .= "market watch <item name or aoid>\n";
		$out .= "  Add an item to your personal watchlist. You'll get a tell as soon as a new order is\n";
		$out .= "  posted for it - immediately if you're online, or the next time you log on if you weren't.\n";
		$out .= "  Requires " . $tools->chatcmd("market register", "registering") . " first.\n";
		$out .= "  Capped at " . $limit . " item(s) per player (admin-configurable).\n\n";
		$out .= "market unwatch <aoid>\n";
		$out .= "  Stop watching an item. Doesn't affect anyone else still watching it.\n\n";
		$out .= "market watchlist\n";
		$out .= "  List everything currently on your watchlist, with quick links to unwatch any of them.\n\n";
		$out .= "Notes:\n";
		$out .= " - The first price check right after you start watching an item never alerts on orders\n";
		$out .= "   that already existed - only genuinely new ones from then on count.\n";
		$out .= " - \"New\" is judged by price/QL/quantity/party, since the market API has no listing ID -\n";
		$out .= "   so an identical relisting after the original expired will look new again.\n\n";
		$out .= "[" . $tools->chatcmd("market help", "Back to Market Help") . "]";
		return $tools->make_blob("Market Help: Watchlist & Alerts", $out);
	}

	function help_status()
	{
		$tools = $this->bot->core("tools");
		$out = "__________Tracking Status_________\n\n";
		$out .= "market status\n";
		$out .= "  Shows an overview of price-history tracking: current settings and how many items\n";
		$out .= "  are tracked, broken down into [Auto] (one of the most actively-traded items, resynced\n";
		$out .= "  from ao-stonks.com) vs [Manual] (something someone looked up or watched).\n\n";
		$out .= "market status details\n";
		$out .= "  Lists every individual tracked item and when it was last polled. Slower than\n";
		$out .= "  market status since it has to list every item, so use it only when you need the detail.\n\n";
		$out .= "[" . $tools->chatcmd("market help", "Back to Market Help") . "]";
		return $tools->make_blob("Market Help: Tracking Status", $out);
	}

	function help_stats()
	{
		$tools = $this->bot->core("tools");
		$out = "__________Your Stats_________\n\n";
		$out .= "market user stats\n";
		$out .= "  Your own Market usage: total actions, when you first showed up, your active watchlist\n";
		$out .= "  count, and a breakdown by action type (search/overview/watch/unwatch/status/etc).\n\n";
		$out .= "market user stats <player>\n";
		$out .= "  ADMIN+ only - the same breakdown for any other player.\n\n";
		$out .= "[" . $tools->chatcmd("market help", "Back to Market Help") . "]";
		return $tools->make_blob("Market Help: Your Stats", $out);
	}

	/*
	Gated inline rather than via register_command()'s subcommand levels, since the framework's
	subcommand matching only sees the second word of the message ("help") and can't distinguish
	"market help settings" from "market help search" - both are subcommand "help" to it.
	*/
	function help_settings($name)
	{
		if (!$this->bot->core("security")->check_access($name, "ADMIN")) {
			return "Only ADMIN+ can view Market settings. Try " . $this->bot->core("tools")->chatcmd("market help", "market help") . " for other topics.";
		}
		$tools = $this->bot->core("tools");
		$settings = $this->bot->core("settings");
		$rows = array(
			array("Market.Enabled", "Whether the module responds to commands and tracks prices at all"),
			array("Market.ApiUrl", "GMI search API URL"),
			array("Market.PollIntervalMinutes", "How often watched items are re-polled to build price history"),
			array("Market.HistoryRetentionDays", "How many days of price history are kept per item"),
			array("Market.WatchExpireDays", "Stop polling an item nobody's looked up/watched again within this many days"),
			array("Market.PollBatchSize", "Max items re-polled per timer cycle"),
			array("Market.AutoTrackEnabled", "Auto-track the most actively-traded items"),
			array("Market.AutoTrackCount", "How many top-traded items to auto-track"),
			array("Market.AutoTrackIntervalMinutes", "How often the auto-tracked list is resynced"),
			array("Market.AutoTrackSourceUrl", "Site used to rank the most actively-traded items"),
			array("Market.MaxSubscriptionsPerPlayer", "Max items a single player can watch at once")
		);
		$out = "__________Settings_________\n";
		$out .= "Changeable by an admin via the bot's settings command.\n\n";
		foreach ($rows as $row) {
			list($module, $setting) = explode(".", $row[0]);
			$value = $settings->get($module, $setting);
			$display = is_bool($value) ? ($value ? "On" : "Off") : (string) $value;
			$out .= $this->tab($row[0], 34) . " = " . $this->tab($display, 12) . " " . $row[1] . "\n";
		}
		$out .= "\n[" . $tools->chatcmd("market help", "Back to Market Help") . "]";
		return $tools->make_blob("Market Help: Settings", $out);
	}

	/*
	Local aorefs word-search, same approach as Gmi.php::gmi_check but with escaped search terms
	(Gmi.php's own version does not escape - avoiding that mistake here) and including the icon
	column so results can be presented as itemref/icon links.
	*/
	function search_items($search, $commandPrefix = "market", $label = "Overview")
	{
		$words = preg_split('/\s+/', strtolower(trim($search)));
		$where = array();
		foreach ($words as $word) {
			if ($word === "") {
				continue;
			}
			$where[] = "LOWER(name) LIKE '%" . $this->bot->db->real_escape_string($word) . "%'";
		}
		if (empty($where)) {
			return "Usage: market <item name>  or  market <aoid>";
		}
		$query = "SELECT id, name, ql, icon FROM aorefs WHERE " . implode(" AND ", $where) . " ORDER BY ql DESC LIMIT 40";
		$refs = $this->bot->db->select($query);
		if (empty($refs)) {
			return "No searchable item(s) found corresponding to your keyword(s)";
		}
		$inside = "";
		foreach ($refs as $ref) {
			$inside .= "<img src=rdb://" . $ref[3] . "> " . $ref[1] . " QL" . $ref[2] . " ["
				. $this->bot->core("tools")->chatcmd($commandPrefix . " " . $ref[0], $label) . "]\n";
		}
		return count($refs) . " matching item(s) : " . $this->bot->core("tools")->make_blob("click to view", $inside);
	}

	/*
	Full per-item overview: header/links, live market summary + order list (same GMI API Gmi.php
	uses), and a locally-tracked price-history trend (the API itself has no history endpoint).
	*/
	function show_overview($name, $aoid)
	{
		$item = $this->bot->db->select("SELECT id, name, ql, icon FROM aorefs WHERE id = " . $aoid . " LIMIT 1");
		if (empty($item)) {
			return "Unknown item ID " . $aoid . ". Try 'market <item name>' to search first.";
		}
		list($id, $itemName, $ql, $icon) = $item[0];

		$this->watch($id, $itemName, $ql, $icon);

		$linkName = $this->chatcmd_safe($itemName);
		$inside = "<img src=rdb://" . $icon . "> <a href='itemref://" . $id . "/" . $id . "/" . $ql . "'>" . $itemName . "</a> QL" . $ql . "\n";
		$inside .= "[" . $this->bot->core("tools")->chatcmd("items " . $linkName, "Full Item Info") . "]"
			. " [" . $this->bot->core("tools")->chatcmd("gmi " . $id . " " . $linkName, "Full Order List") . "]\n\n";

		$orders = $this->fetch_orders($id);
		if ($orders === false) {
			$inside .= "Market data currently unavailable, please try again later.\n\n";
		} else {
			$inside .= $this->render_summary($orders);
			$inside .= "\n";
			$inside .= $this->render_ql_table($orders, $id, $ql);
			$inside .= "\n";
			$inside .= $this->render_orders($orders);
		}

		return $this->bot->core("tools")->make_blob(":: " . $itemName . " :: Market Overview", $inside);
	}

	function watch($aoid, $name, $ql, $icon)
	{
		$name = $this->bot->db->real_escape_string($name);
		$now = time();
		$this->bot->db->query(
			"INSERT INTO #___market_watch (aoid, name, ql, icon, first_seen, last_polled) VALUES ("
				. $aoid . ", '" . $name . "', " . intval($ql) . ", " . intval($icon) . ", " . $now . ", 0)"
			. " ON DUPLICATE KEY UPDATE name = '" . $name . "', ql = " . intval($ql) . ", icon = " . intval($icon)
		);
	}

	/*
	Personal watchlist subscription (distinct from watch() above, which just controls whether the
	bot polls an item at all - this is "does this specific player want a tell about it"). Requires
	having run !market register first (Market's own self-service opt-in, see cmd_register()).
	*/
	function cmd_watch($name, $aoid)
	{
		$item = $this->bot->db->select("SELECT id, name, ql, icon FROM aorefs WHERE id = " . $aoid . " LIMIT 1");
		if (empty($item)) {
			return "Unknown item ID " . $aoid . ". Try 'market watch <item name>' to search first.";
		}
		list($id, $itemName, $ql, $icon) = $item[0];

		if (!$this->is_registered($name)) {
			$this->log_action($name, "watch_denied", $id);
			return "You need to register first - try " . $this->bot->core("tools")->chatcmd("market register", "market register") . ".";
		}

		$nameEsc = $this->bot->db->real_escape_string($name);
		$existing = $this->bot->db->select(
			"SELECT id FROM #___market_subscriptions WHERE player = '" . $nameEsc . "' AND aoid = " . $id
		);
		if (!empty($existing)) {
			return "You're already watching " . $itemName . " (QL" . $ql . ").";
		}

		$limit = intval($this->bot->core("settings")->get("Market", "MaxSubscriptionsPerPlayer"));
		$count = $this->bot->db->select(
			"SELECT COUNT(*) FROM #___market_subscriptions WHERE player = '" . $nameEsc . "'"
		);
		if ((int) $count[0][0] >= $limit) {
			return "You're already watching the maximum of " . $limit . " item(s). Unwatch something first with 'market unwatch <aoid>'.";
		}

		$this->bot->db->query(
			"INSERT INTO #___market_subscriptions (player, aoid, side, created_at) VALUES ('"
				. $nameEsc . "', " . $id . ", 'any', " . time() . ")"
		);
		$this->watch($id, $itemName, $ql, $icon);
		$this->log_action($name, "watch", $id);

		return "You're now watching " . $itemName . " (QL" . $ql . ") - you'll get a tell when a new order shows up. ["
			. $this->bot->core("tools")->chatcmd("market watchlist", "View Watchlist") . "]";
	}

	function cmd_unwatch($name, $aoid)
	{
		$item = $this->bot->db->select("SELECT name FROM aorefs WHERE id = " . intval($aoid) . " LIMIT 1");
		$itemName = !empty($item) ? $item[0][0] : ("AOID " . $aoid);

		$deleted = $this->bot->db->returnQuery(
			"DELETE FROM #___market_subscriptions WHERE player = '" . $this->bot->db->real_escape_string($name) . "' AND aoid = " . intval($aoid)
		);
		$this->log_action($name, "unwatch", intval($aoid));

		if ($deleted) {
			return "Stopped watching " . $itemName . ".";
		}
		return "You weren't watching " . $itemName . ".";
	}

	/*
	Lists everything the caller is currently subscribed to. LEFT JOINs aorefs defensively (same
	fallback as cmd_unwatch's message) in case an item's local aorefs row is ever missing/pruned.
	*/
	function show_watchlist($name)
	{
		$rows = $this->bot->db->select(
			"SELECT s.aoid, a.name, a.ql, a.icon, s.created_at FROM #___market_subscriptions s"
			. " LEFT JOIN aorefs a ON a.id = s.aoid"
			. " WHERE s.player = '" . $this->bot->db->real_escape_string($name) . "'"
			. " ORDER BY s.created_at ASC"
		);
		$tools = $this->bot->core("tools");
		if (empty($rows)) {
			return "Your watchlist is empty. Try " . $tools->chatcmd("market help watch", "market help watch") . " for how to add items.";
		}

		$now = time();
		$inside = "";
		foreach ($rows as $row) {
			list($aoid, $itemName, $ql, $icon, $createdAt) = $row;
			$itemName = $itemName !== null ? $itemName : ("AOID " . $aoid);
			$ql = $ql !== null ? $ql : 1;
			$icon = $icon !== null ? $icon : 0;
			$inside .= "<img src=rdb://" . $icon . "> <a href='itemref://" . $aoid . "/" . $aoid . "/" . $ql . "'>" . $itemName . "</a> QL" . $ql
				. " - watching " . $this->bot->core("time")->format_seconds($now - $createdAt) . " ["
				. $tools->chatcmd("market " . $aoid, "Overview") . "] ["
				. $tools->chatcmd("market unwatch " . $aoid, "Unwatch") . "]\n";
		}

		$limit = intval($this->bot->core("settings")->get("Market", "MaxSubscriptionsPerPlayer"));
		$out = count($rows) . " of " . $limit . " item(s) watched:\n\n" . $inside;
		return $tools->make_blob("Your Watchlist", $out);
	}

	/*
	Called by Core/LogonNotifies.php once a player with #___users.notify=1 logs back on - drains
	any tells that couldn't be delivered live because they were offline when a watched item's new
	order was detected (see detect_new_orders()/notify_subscribers() below).
	*/
	function notify($nickname, $startup)
	{
		$nameEsc = $this->bot->db->real_escape_string($nickname);
		$pending = $this->bot->db->select(
			"SELECT id, message FROM #___market_pending_alerts WHERE player = '" . $nameEsc . "' ORDER BY created_at ASC"
		);
		foreach ($pending as $row) {
			$this->bot->send_tell($nickname, $row[1]);
			$this->bot->db->query("DELETE FROM #___market_pending_alerts WHERE id = " . intval($row[0]));
		}
	}

	function show_user_stats($caller, $target = null)
	{
		if ($target !== null) {
			if (!$this->bot->core("security")->check_access($caller, "ADMIN")) {
				return "Only ADMIN+ can look up another player's market stats.";
			}
			$player = $target;
		} else {
			$player = $caller;
		}
		$playerEsc = $this->bot->db->real_escape_string($player);

		$total = $this->bot->db->select(
			"SELECT COUNT(*), MIN(created_at) FROM #___market_user_actions WHERE player = '" . $playerEsc . "'"
		);
		if (empty($total) || $total[0][0] == 0) {
			return $player . " has no recorded Market activity.";
		}
		$byAction = $this->bot->db->select(
			"SELECT action, COUNT(*) FROM #___market_user_actions WHERE player = '" . $playerEsc . "' GROUP BY action ORDER BY COUNT(*) DESC"
		);
		$subs = $this->bot->db->select(
			"SELECT COUNT(*) FROM #___market_subscriptions WHERE player = '" . $playerEsc . "'"
		);

		$out = "__________Market Activity: " . $player . "_________\n";
		$out .= "Total actions        : " . $total[0][0] . "\n";
		$out .= "First seen           : " . date("Y-m-d", $total[0][1]) . " (" . $this->bot->core("time")->format_seconds(time() - $total[0][1]) . " ago)\n";
		$out .= "Active subscriptions : " . (!empty($subs) ? (int) $subs[0][0] : 0) . "\n\n";
		$out .= $this->tab("ACTION", 14) . "COUNT\n";
		foreach ($byAction as $row) {
			$out .= $this->tab(ucfirst($row[0]), 14) . $row[1] . "\n";
		}
		return $this->bot->core("tools")->make_blob("Market Stats", $out);
	}

	function render_summary($orders)
	{
		$bestSell = null;
		$bestBuy = null;
		foreach ($orders->sell_orders as $sell) {
			if ($bestSell === null || $sell->price < $bestSell) {
				$bestSell = $sell->price;
			}
		}
		foreach ($orders->buy_orders as $buy) {
			if ($bestBuy === null || $buy->price > $bestBuy) {
				$bestBuy = $buy->price;
			}
		}
		$out = "__________Market Summary_________\n";
		$out .= "Lowest sell / Highest buy : " . ($bestSell !== null ? $this->format_credits($bestSell) : "-")
			. "  /  " . ($bestBuy !== null ? $this->format_credits($bestBuy) : "-") . "\n";
		if ($bestSell !== null && $bestBuy !== null) {
			$out .= "Spread                    : " . $this->format_credits($bestSell - $bestBuy) . "\n";
		}
		$out .= "Orders                    : " . count($orders->sell_orders) . " sell / " . count($orders->buy_orders) . " buy\n";
		$out .= "Last updated              : " . date("Y-m-d H:i:s") . " UTC\n";
		return $out;
	}

	function history_average($aoid, $since, $until)
	{
		$base = " FROM #___market_history WHERE aoid = " . intval($aoid) . " AND ts >= " . intval($since) . " AND ts < " . intval($until);
		$sell = $this->bot->db->select("SELECT AVG(avg_sell_price), COUNT(*)" . $base . " AND anchor_sell_count > 0");
		$buy = $this->bot->db->select("SELECT AVG(avg_buy_price), COUNT(*)" . $base . " AND anchor_buy_count > 0");
		$total = $this->bot->db->select("SELECT COUNT(*)" . $base);
		if (empty($total) || $total[0][0] == 0) {
			return null;
		}
		return array(
			'avg_sell' => (!empty($sell) && $sell[0][1] > 0) ? (float) $sell[0][0] : null,
			'avg_buy' => (!empty($buy) && $buy[0][1] > 0) ? (float) $buy[0][0] : null,
			'count' => (int) $total[0][0]
		);
	}

	function format_trend($current, $previous)
	{
		if ($previous === null || $previous == 0) {
			return "";
		}
		$change = (($current - $previous) / $previous) * 100;
		$sign = $change >= 0 ? "+" : "";
		return $sign . round($change, 1) . "%";
	}

	/*
	Buckets the current live orders into 50-QL bands and shows avg price + price/QL per band, since
	a single AOID's orders can span very different QLs and a blended average is meaningless. The band
	containing the item's own QL is starred, and carries the one thing that IS tracked historically
	(via history_average(), anchored to that exact QL) as a 7-day trend - other bands only ever show
	live-right-now data, since we don't track history at any QL but the item's own.
	*/
	function render_ql_table($orders, $aoid, $anchorQl)
	{
		$bandSize = 50;
		$buckets = array();

		foreach ($orders->sell_orders as $sell) {
			$band = (int) floor(($sell->ql - 1) / $bandSize);
			if (!isset($buckets[$band])) {
				$buckets[$band] = array('sell' => array(), 'buy' => array());
			}
			$buckets[$band]['sell'][] = $sell->price;
		}
		foreach ($orders->buy_orders as $buy) {
			$lowBand = (int) floor(($buy->min_ql - 1) / $bandSize);
			$highBand = (int) floor(($buy->max_ql - 1) / $bandSize);
			for ($band = $lowBand; $band <= $highBand; $band++) {
				if (!isset($buckets[$band])) {
					$buckets[$band] = array('sell' => array(), 'buy' => array());
				}
				$buckets[$band]['buy'][] = $buy->price;
			}
		}

		$anchorBand = (int) floor(($anchorQl - 1) / $bandSize);
		if (!isset($buckets[$anchorBand])) {
			$buckets[$anchorBand] = array('sell' => array(), 'buy' => array());
		}
		ksort($buckets);

		$now = time();
		$recent = $this->history_average($aoid, $now - (7 * 86400), $now);
		$prior = $this->history_average($aoid, $now - (14 * 86400), $now - (7 * 86400));

		$out = "__________Price by QL Band_________ (* = QL" . $anchorQl . ", this item)\n";
		$out .= $this->tab("BAND", 12) . " " . $this->tab("AVG SELL", 12) . " " . $this->tab("AVG BUY", 12)
			. " " . $this->tab("SELL/QL", 9) . " " . $this->tab("BUY/QL", 9) . " " . "7D TREND" . "\n";

		foreach ($buckets as $band => $data) {
			$lowQl = $band * $bandSize + 1;
			$highQl = $lowQl + $bandSize - 1;
			$midQl = ($lowQl + $highQl) / 2;
			$avgSell = !empty($data['sell']) ? array_sum($data['sell']) / count($data['sell']) : null;
			$avgBuy = !empty($data['buy']) ? array_sum($data['buy']) / count($data['buy']) : null;
			$isAnchor = ($band == $anchorBand);
			$label = ($isAnchor ? "*" : "") . "QL" . $lowQl . "-" . $highQl;

			if (!$isAnchor) {
				$trend = "-";
			} elseif ($recent === null) {
				$trend = "tracking just started";
			} else {
				$parts = array();
				if ($recent['avg_sell'] !== null) {
					$t = $this->format_trend($recent['avg_sell'], $prior['avg_sell'] ?? null);
					$parts[] = "sell " . ($t !== "" ? $t : "n/a");
				}
				if ($recent['avg_buy'] !== null) {
					$t = $this->format_trend($recent['avg_buy'], $prior['avg_buy'] ?? null);
					$parts[] = "buy " . ($t !== "" ? $t : "n/a");
				}
				$trend = !empty($parts) ? implode(", ", $parts) : "no data yet";
			}

			$out .= $this->tab($label, 12) . " "
				. $this->tab($avgSell !== null ? $this->format_credits($avgSell) : "-", 12) . " "
				. $this->tab($avgBuy !== null ? $this->format_credits($avgBuy) : "-", 12) . " "
				. $this->tab($avgSell !== null ? $this->format_credits($avgSell / $midQl) : "-", 9) . " "
				. $this->tab($avgBuy !== null ? $this->format_credits($avgBuy / $midQl) : "-", 9) . " "
				. $trend . "\n";
		}
		return $out;
	}

	function render_orders($orders)
	{
		$out = "";
		$sells = $orders->sell_orders;
		usort($sells, function ($a, $b) {
			return $a->price <=> $b->price;
		});
		$buys = $orders->buy_orders;
		usort($buys, function ($a, $b) {
			return $b->price <=> $a->price;
		});
		$limit = 5;

		if (!empty($sells)) {
			$out .= "__________Cheapest SELL Orders_________\n";
			$out .= $this->tab("PRICE", 15) . " " . $this->tab("QL", 5) . " " . $this->tab("COUNT", 5) . " " . $this->tab("SELLER", 18) . "\n";
			foreach (array_slice($sells, 0, $limit) as $sell) {
				$out .= $this->tab($this->format_credits($sell->price), 15) . " " . $this->tab($sell->ql, 5) . " " . $this->tab($sell->count, 5) . " " . $this->tab($sell->seller, 18) . "\n";
			}
			if (count($sells) > $limit) {
				$out .= "... and " . (count($sells) - $limit) . " more (see Full Order List)\n";
			}
			$out .= "\n";
		} else {
			$out .= "No SELL order(s) for now ...\n\n";
		}

		if (!empty($buys)) {
			$out .= "__________Highest BUY Orders__________\n";
			$out .= $this->tab("PRICE", 15) . " " . $this->tab("MIN QL", 6) . " " . $this->tab("MAX QL", 6) . " " . $this->tab("BUYER", 18) . "\n";
			foreach (array_slice($buys, 0, $limit) as $buy) {
				$out .= $this->tab($this->format_credits($buy->price), 15) . " " . $this->tab($buy->min_ql, 6) . " " . $this->tab($buy->max_ql, 6) . " " . $this->tab($buy->buyer, 18) . "\n";
			}
			if (count($buys) > $limit) {
				$out .= "... and " . (count($buys) - $limit) . " more (see Full Order List)\n";
			}
		} else {
			$out .= "No BUY order(s) for now ...\n";
		}
		return $out;
	}

	function fetch_orders($aoid)
	{
		$url = rtrim($this->bot->core("settings")->get("Market", "ApiUrl"), "/") . "/v1.0/aoid/" . intval($aoid);
		$this->bot->log("MARKET", "FETCH", "GET " . $url);
		$content = $this->bot->core("tools")->get_site($url);
		if ($content instanceof BotError) {
			$this->bot->log("MARKET", "FETCH", "Failed fetching AOID " . $aoid . " from " . $url . ": " . $content->message(), true);
			return false;
		}
		$data = json_decode($content);
		if (!is_object($data) || (!isset($data->buy_orders) && !isset($data->sell_orders))) {
			$this->bot->log("MARKET", "FETCH", "Unexpected response fetching AOID " . $aoid . " from " . $url, true);
			return false;
		}
		if (!isset($data->buy_orders)) {
			$data->buy_orders = array();
		}
		if (!isset($data->sell_orders)) {
			$data->sell_orders = array();
		}
		$this->bot->log("MARKET", "FETCH", "AOID " . $aoid . ": " . count($data->sell_orders) . " sell / " . count($data->buy_orders) . " buy order(s)");
		return $data;
	}

	function format_credits($value)
	{
		$value = (float) $value;
		$sign = $value < 0 ? "-" : "";
		$value = abs($value);
		if ($value >= 1000000000) {
			return $sign . round($value / 1000000000, 1) . "b";
		} elseif ($value >= 1000000) {
			return $sign . round($value / 1000000, 1) . "m";
		} elseif ($value >= 1000) {
			return $sign . round($value / 1000, 1) . "k";
		}
		return $sign . number_format($value, 0);
	}

	/*
	chatcmd() (Main/14_Tools.php) builds an unescaped href='...' - a literal apostrophe in $text
	(e.g. "Keeper's Physique") breaks that attribute and garbles the whole link. Same workaround
	already used elsewhere in the codebase for item names in chatcmd/itemref links, e.g.
	Modules/Ao/Bank.php's str_replace('\'','`',...).
	*/
	function chatcmd_safe($text)
	{
		return str_replace("'", "`", $text);
	}

	function tab($value, $length)
	{
		if (strlen($value) < $length) {
			$diff = $length - strlen($value);
			for ($i = 0; $i < $diff; $i++) {
				$value .= "&nbsp;";
			}
			return $value;
		} else {
			return $value;
		}
	}

	/*
	Fired by TimerCore ("internal" channel timers call back into whichever module registered
	itself for the timer's owner name - see Modules/Irc.php for the same registration pattern).
	*/
	function timer($name, $prefix, $suffix, $delay)
	{
		if (!$this->bot->core("settings")->get("Market", "Enabled")) {
			return;
		}
		if ($name == "Market-Poll") {
			$this->poll_market();
		} elseif ($name == "Market-AutoTrack") {
			$this->sync_top_traded_items();
		}
	}

	function poll_market()
	{
		$now = time();
		$retentionSeconds = 86400 * intval($this->bot->core("settings")->get("Market", "HistoryRetentionDays"));
		$expireSeconds = 86400 * intval($this->bot->core("settings")->get("Market", "WatchExpireDays"));
		$intervalSeconds = 60 * intval($this->bot->core("settings")->get("Market", "PollIntervalMinutes"));
		$batchSize = intval($this->bot->core("settings")->get("Market", "PollBatchSize"));

		// Drop items nobody has re-searched for within the expiry window, and their history with them.
		// Auto-tracked items are exempt - they're removed explicitly by sync_top_traded_items() instead,
		// once they actually fall out of the top-traded list.
		$expired = $this->bot->db->select(
			"SELECT aoid FROM #___market_watch WHERE auto_tracked = 0 AND GREATEST(last_polled, first_seen) < " . ($now - $expireSeconds)
		);
		foreach ($expired as $row) {
			$this->bot->db->query("DELETE FROM #___market_history WHERE aoid = " . intval($row[0]));
			$this->bot->db->query("DELETE FROM #___market_watch WHERE aoid = " . intval($row[0]));
		}
		if (!empty($expired)) {
			$this->bot->log("MARKET", "POLL", "Expired " . count($expired) . " unwatched item(s) past WatchExpireDays", true);
		}

		// Prune old history snapshots.
		$this->bot->db->query("DELETE FROM #___market_history WHERE ts < " . ($now - $retentionSeconds));

		// Re-poll the items most overdue for a refresh.
		$due = $this->bot->db->select(
			"SELECT aoid, ql, name FROM #___market_watch WHERE last_polled < " . ($now - $intervalSeconds)
			. " ORDER BY last_polled ASC LIMIT " . $batchSize
		);
		$this->bot->log("MARKET", "POLL", "Poll cycle: " . count($due) . " item(s) due for refresh");
		$updated = 0;
		foreach ($due as $row) {
			$aoid = intval($row[0]);
			$anchorQl = intval($row[1]);
			$itemName = $row[2];
			$orders = $this->fetch_orders($aoid);
			if ($orders !== false) {
				$this->snapshot($aoid, $orders, $anchorQl);
				$this->detect_new_orders($aoid, $orders, $itemName);
				$updated++;
			}
			$this->bot->db->query("UPDATE #___market_watch SET last_polled = " . $now . " WHERE aoid = " . $aoid);
		}
		if (count($due) > 0) {
			$this->bot->log("MARKET", "POLL", "Poll cycle complete: " . $updated . "/" . count($due) . " item(s) successfully updated", true);
		}
	}

	/*
	"Is this a new order" has no help from the API - GMI order objects carry no stable ID (just
	count/price/min_ql-max_ql/buyer-or-seller/expiration). Fingerprints exclude `expiration` (it
	counts down every poll, which would make every order look new every cycle) but include `count`
	(static for a given listing, unlike expiration, so it still helps distinguish genuinely separate
	orders at the same price/QL). The seen-set is fully rebuilt every cycle rather than aged out, so
	there's no separate pruning job and a relisted-identical order after a real gap is treated as new.
	*/
	function detect_new_orders($aoid, $orders, $itemName)
	{
		$fingerprints = array();
		foreach ($orders->sell_orders as $sell) {
			$fingerprints[] = "sell|" . $sell->price . "|" . $sell->ql . "|" . $sell->count . "|" . $sell->seller;
		}
		foreach ($orders->buy_orders as $buy) {
			$fingerprints[] = "buy|" . $buy->price . "|" . $buy->min_ql . "|" . $buy->max_ql . "|" . $buy->count . "|" . $buy->buyer;
		}
		$fingerprints = array_unique($fingerprints);

		$seen = $this->bot->db->select(
			"SELECT fingerprint FROM #___market_seen_orders WHERE aoid = " . intval($aoid)
		);
		$isFirstPoll = empty($seen);
		if (!$isFirstPoll) {
			$seenSet = array();
			foreach ($seen as $row) {
				$seenSet[$row[0]] = true;
			}
			$newFingerprints = array_diff($fingerprints, array_keys($seenSet));
			if (!empty($newFingerprints)) {
				$this->notify_subscribers($aoid, $itemName, count($newFingerprints));
			}
		}

		$this->bot->db->query("DELETE FROM #___market_seen_orders WHERE aoid = " . intval($aoid));
		foreach ($fingerprints as $fp) {
			$this->bot->db->query(
				"INSERT IGNORE INTO #___market_seen_orders (aoid, fingerprint) VALUES (" . intval($aoid) . ", '"
					. $this->bot->db->real_escape_string($fp) . "')"
			);
		}
	}

	function notify_subscribers($aoid, $itemName, $newOrderCount)
	{
		$subs = $this->bot->db->select(
			"SELECT player FROM #___market_subscriptions WHERE aoid = " . intval($aoid)
		);
		if (empty($subs)) {
			return;
		}
		// A bare chatcmd() link sent directly as a tell does NOT render as clickable - every
		// working example elsewhere in the codebase (Modules/Raffle.php's click_join(),
		// Modules/AltsUi.php's alt confirmation tell) wraps it in make_blob() first.
		$tools = $this->bot->core("tools");
		$inside = $newOrderCount . " new order(s) posted for " . $itemName . ".\n\n["
			. $tools->chatcmd("market " . $aoid, "View Overview") . "]";
		$message = $tools->make_blob($itemName . " - New Order(s)", $inside);

		foreach ($subs as $row) {
			$player = $row[0];
			if ($this->bot->core("chat")->buddy_online($player)) {
				$this->bot->send_tell($player, $message);
			} else {
				$this->bot->db->query(
					"INSERT INTO #___market_pending_alerts (player, aoid, message, created_at) VALUES ('"
						. $this->bot->db->real_escape_string($player) . "', " . intval($aoid) . ", '"
						. $this->bot->db->real_escape_string($message) . "', " . time() . ")"
				);
			}
		}
		$this->bot->log("MARKET", "ALERT", "AOID " . $aoid . ": notified " . count($subs) . " subscriber(s) of " . $newOrderCount . " new order(s)", true);
	}

	/*
	sell_count/buy_count/min_sell_price/max_buy_price cover ALL orders regardless of QL - that's
	the correct "observed range" data. avg_sell_price/avg_buy_price are anchored to $anchorQl (the
	item's own QL) since a single AOID's orders can span wildly different QLs and a blended average
	across all of them is meaningless. anchor_*_count records how many orders matched that QL this
	cycle, so a cycle with zero matches doesn't get treated as a real price of 0 downstream.
	*/
	function snapshot($aoid, $orders, $anchorQl)
	{
		$sellCount = count($orders->sell_orders);
		$buyCount = count($orders->buy_orders);
		$minSell = 0;
		if ($sellCount > 0) {
			$prices = array_map(function ($o) {
				return $o->price;
			}, $orders->sell_orders);
			$minSell = min($prices);
		}
		$maxBuy = 0;
		if ($buyCount > 0) {
			$prices = array_map(function ($o) {
				return $o->price;
			}, $orders->buy_orders);
			$maxBuy = max($prices);
		}

		$anchorSellPrices = array_map(function ($o) {
			return $o->price;
		}, array_filter($orders->sell_orders, function ($o) use ($anchorQl) {
			return $o->ql == $anchorQl;
		}));
		$anchorBuyPrices = array_map(function ($o) {
			return $o->price;
		}, array_filter($orders->buy_orders, function ($o) use ($anchorQl) {
			return $o->min_ql <= $anchorQl && $anchorQl <= $o->max_ql;
		}));
		$anchorSellCount = count($anchorSellPrices);
		$anchorBuyCount = count($anchorBuyPrices);
		$avgSell = $anchorSellCount > 0 ? array_sum($anchorSellPrices) / $anchorSellCount : 0;
		$avgBuy = $anchorBuyCount > 0 ? array_sum($anchorBuyPrices) / $anchorBuyCount : 0;

		$this->bot->db->query(
			"INSERT INTO #___market_history (aoid, ts, sell_count, buy_count, min_sell_price, max_buy_price, avg_sell_price, avg_buy_price, anchor_sell_count, anchor_buy_count) VALUES ("
				. intval($aoid) . ", " . time() . ", " . $sellCount . ", " . $buyCount . ", "
				. intval($minSell) . ", " . intval($maxBuy) . ", " . intval($avgSell) . ", " . intval($avgBuy) . ", "
				. $anchorSellCount . ", " . $anchorBuyCount . ")"
		);
		$this->bot->log(
			"MARKET",
			"SNAPSHOT",
			"AOID " . $aoid . " (anchor QL" . $anchorQl . "): recorded " . $sellCount . " sell / " . $buyCount . " buy order(s), "
				. $anchorSellCount . " sell / " . $anchorBuyCount . " matching anchor QL"
		);
	}

	/*
	Auto-tracks the most actively-traded items, sourced from ao-stonks.com's default item listing
	(sorted by open buy-order count descending - confirmed via direct inspection that /items/{page}
	server-renders 20 items per page in that order, while its "Per Page"/sort controls are
	client-JS-driven and have no effect on a plain GET, making page-by-page fetching the only
	reliable way to pull a ranked list here).
	*/
	function sync_top_traded_items()
	{
		if (!$this->bot->core("settings")->get("Market", "AutoTrackEnabled")) {
			return;
		}
		$count = intval($this->bot->core("settings")->get("Market", "AutoTrackCount"));
		if ($count < 1) {
			return;
		}
		$maxPages = 50; // hard safety ceiling regardless of configured count (50 * 20 = 1000 items)
		$pages = min($maxPages, (int) ceil($count / 20));
		$sourceUrl = rtrim($this->bot->core("settings")->get("Market", "AutoTrackSourceUrl"), "/");

		$this->bot->log("MARKET", "AUTOTRACK", "Resyncing top " . $count . " traded item(s) from " . $sourceUrl, true);
		$aoids = array();
		$pagesFetched = 0;
		for ($page = 1; $page <= $pages; $page++) {
			$pageUrl = $sourceUrl . "/items/" . $page;
			$this->bot->log("MARKET", "AUTOTRACK", "GET " . $pageUrl);
			$content = $this->bot->core("tools")->get_site($pageUrl);
			if ($content instanceof BotError) {
				$this->bot->log("MARKET", "AUTOTRACK", "Failed fetching " . $pageUrl . ": " . $content->message(), true);
				break;
			}
			if (!preg_match_all('/class="item-name"\s+href="\/item\/([0-9]+)"/i', $content, $matches)) {
				$this->bot->log("MARKET", "AUTOTRACK", "No items parsed from " . $pageUrl . " - stopping this cycle", true);
				break;
			}
			$pagesFetched++;
			foreach ($matches[1] as $aoid) {
				$aoid = intval($aoid);
				if (!in_array($aoid, $aoids, true)) {
					$aoids[] = $aoid;
				}
			}
			if (count($aoids) >= $count) {
				break;
			}
		}

		// A transient outage (or a markup change breaking the parser) shouldn't wipe out the
		// existing auto-tracked set - only proceed if we actually got at least one page of results.
		if ($pagesFetched == 0) {
			$this->bot->log("MARKET", "AUTOTRACK", "Could not fetch item ranking from " . $sourceUrl . ", skipping this cycle.", true);
			return;
		}

		$aoids = array_slice($aoids, 0, $count);
		$resolved = array();
		if (!empty($aoids)) {
			$refs = $this->bot->db->select(
				"SELECT id, name, ql, icon FROM aorefs WHERE id IN (" . implode(",", $aoids) . ")"
			);
			foreach ($refs as $ref) {
				$resolved[(int) $ref[0]] = array('name' => $ref[1], 'ql' => (int) $ref[2], 'icon' => (int) $ref[3]);
			}
		}

		$now = time();
		if (empty($resolved)) {
			$this->bot->db->query("UPDATE #___market_watch SET auto_tracked = 0 WHERE auto_tracked = 1");
		} else {
			$this->bot->db->query(
				"UPDATE #___market_watch SET auto_tracked = 0 WHERE auto_tracked = 1 AND aoid NOT IN (" . implode(",", array_keys($resolved)) . ")"
			);
		}
		foreach ($resolved as $aoid => $item) {
			$name = $this->bot->db->real_escape_string($item['name']);
			$this->bot->db->query(
				"INSERT INTO #___market_watch (aoid, name, ql, icon, first_seen, last_polled, auto_tracked) VALUES ("
					. $aoid . ", '" . $name . "', " . $item['ql'] . ", " . $item['icon'] . ", " . $now . ", 0, 1)"
				. " ON DUPLICATE KEY UPDATE name = '" . $name . "', ql = " . $item['ql'] . ", icon = " . $item['icon'] . ", auto_tracked = 1"
			);
		}

		$this->bot->core("settings")->save("Market", "AutoTrackLastSync", $now);
		$this->bot->log(
			"MARKET",
			"AUTOTRACK",
			"Resync complete: " . $pagesFetched . " page(s) fetched, " . count($aoids) . " ranked AOID(s) found, "
				. count($resolved) . " resolved against local aorefs and now auto-tracked",
			true
		);
	}

	function show_status()
	{
		$enabled = $this->bot->core("settings")->get("Market", "AutoTrackEnabled") ? "On" : "Off";
		$lastSync = intval($this->bot->core("settings")->get("Market", "AutoTrackLastSync"));
		$lastSyncText = ($lastSync > 0) ? $this->bot->core("time")->format_seconds(time() - $lastSync) . " ago" : "never";
		$out = "__________Market Tracking Settings_________\n";
		$out .= "Auto-track          : " . $enabled . " (target " . $this->bot->core("settings")->get("Market", "AutoTrackCount") . " items,"
			. " resync every " . $this->bot->core("settings")->get("Market", "AutoTrackIntervalMinutes") . " min, last resync " . $lastSyncText . ")\n";
		$out .= "Poll interval       : " . $this->bot->core("settings")->get("Market", "PollIntervalMinutes") . " min\n";
		$out .= "History retention  : " . $this->bot->core("settings")->get("Market", "HistoryRetentionDays") . " days\n";
		$out .= "\n";

		$counts = $this->bot->db->select(
			"SELECT COUNT(*), SUM(auto_tracked), SUM(last_polled = 0), MAX(last_polled) FROM #___market_watch"
		);
		list($total, $autoCount, $neverPolled, $lastPolledMax) = $counts[0];
		$total = intval($total);
		if ($total === 0) {
			$out .= "No items are currently tracked.\n";
			return $this->bot->core("tools")->make_blob("Market Status", $out);
		}
		$autoCount = intval($autoCount);
		$manualCount = $total - $autoCount;
		$neverPolled = intval($neverPolled);
		$lastPolledMax = intval($lastPolledMax);
		$lastPolledText = ($lastPolledMax > 0) ? $this->bot->core("time")->format_seconds(time() - $lastPolledMax) . " ago" : "never";

		$out .= "__________Tracked Items Overview_________\n";
		$out .= $total . " item(s) tracked : " . $autoCount . " auto-tracked, " . $manualCount . " manually watched\n";
		$out .= $neverPolled . " item(s) never polled yet\n";
		$out .= "Most recent poll   : " . $lastPolledText . "\n";
		$out .= "\nUse " . $this->bot->core("tools")->chatcmd("market status details", "market status details") . " to list every tracked item.\n";
		return $this->bot->core("tools")->make_blob("Market Status", $out);
	}

	function show_status_details()
	{
		$rows = $this->bot->db->select(
			"SELECT aoid, name, ql, icon, auto_tracked, first_seen, last_polled FROM #___market_watch"
			. " ORDER BY auto_tracked DESC, last_polled DESC LIMIT 500"
		);
		if (empty($rows)) {
			return $this->bot->core("tools")->make_blob("Market Status Details", "No items are currently tracked.\n");
		}

		$now = time();
		$inside = "";
		foreach ($rows as $row) {
			list($aoid, $name, $ql, $icon, $autoTracked, $firstSeen, $lastPolled) = $row;
			$tag = $autoTracked ? "[Auto]" : "[Manual]";
			$updated = ($lastPolled > 0)
				? $this->bot->core("time")->format_seconds($now - $lastPolled) . " ago"
				: "never polled yet";
			$inside .= "<img src=rdb://" . $icon . "> <a href='itemref://" . $aoid . "/" . $aoid . "/" . $ql . "'>" . $name . "</a> QL" . $ql
				. " " . $tag . " - last updated " . $updated . " ["
				. $this->bot->core("tools")->chatcmd("market " . $aoid, "Overview") . "]\n";
		}

		$out = count($rows) . " tracked item(s) :\n\n" . $inside;
		return $this->bot->core("tools")->make_blob("Market Status Details", $out);
	}
}
?>
