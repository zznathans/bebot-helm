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
		$this->register_command("all", "market", "GUEST");
		$this->register_alias("market", "mkt");
		$this->help['description'] = "Market overview: search for an item and see a summary, price history and live orders.";
		$this->help['command']['market <item name>'] = "Search for an item by (partial) name";
		$this->help['command']['market <aoid>'] = "Show the full market overview for a specific item ID";
		$this->help['command']['market status'] = "Show every item currently tracked, its source (auto/manual) and last-updated time";

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

		$this->table();

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
		if ($this->bot->core("settings")->get("Market", "AutoTrackEnabled")) {
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
	}

	function command_handler($name, $msg, $channel)
	{
		if (preg_match('/^(?:market|mkt)\s+status\s*$/i', $msg)) {
			return $this->show_status();
		} elseif (preg_match('/^(?:market|mkt)\s+([0-9]+)\s*$/i', $msg, $info)) {
			return $this->show_overview($name, intval($info[1]));
		} elseif (preg_match('/^(?:market|mkt)\s+(.+)$/i', $msg, $info)) {
			return $this->search_items(trim($info[1]));
		} else {
			return "Usage: market <item name>  or  market <aoid>  or  market status";
		}
	}

	/*
	Local aorefs word-search, same approach as Gmi.php::gmi_check but with escaped search terms
	(Gmi.php's own version does not escape - avoiding that mistake here) and including the icon
	column so results can be presented as itemref/icon links.
	*/
	function search_items($search)
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
				. $this->bot->core("tools")->chatcmd("market " . $ref[0], "Overview") . "]\n";
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
			$inside .= $this->render_history($id, $ql);
			$inside .= "\n";
			$inside .= $this->render_ql_breakdown($orders);
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
		$out .= "Lowest sell price : " . ($bestSell !== null ? $this->format_credits($bestSell) : "-") . "\n";
		$out .= "Highest buy price : " . ($bestBuy !== null ? $this->format_credits($bestBuy) : "-") . "\n";
		if ($bestSell !== null && $bestBuy !== null) {
			$out .= "Spread            : " . $this->format_credits($bestSell - $bestBuy) . "\n";
		}
		$out .= "Sell orders       : " . count($orders->sell_orders) . "\n";
		$out .= "Buy orders        : " . count($orders->buy_orders) . "\n";
		$out .= "Last updated      : " . date("Y-m-d H:i:s") . " UTC\n";
		return $out;
	}

	function render_history($aoid, $anchorQl)
	{
		$now = time();
		$recent = $this->history_average($aoid, $now - (7 * 86400), $now);
		$prior = $this->history_average($aoid, $now - (14 * 86400), $now - (7 * 86400));

		if ($recent === null) {
			return "__________Price History_________\nPrice history tracking just started for this item - check back later.\n";
		}

		$out = "__________Price History (7 days)_________\n";
		$out .= "Avg sell price at QL" . $anchorQl . " : " . ($recent['avg_sell'] !== null
			? $this->format_credits($recent['avg_sell']) . $this->format_trend($recent['avg_sell'], $prior['avg_sell'] ?? null)
			: "no QL" . $anchorQl . " sell orders observed") . "\n";
		$out .= "Avg buy price at QL" . $anchorQl . "  : " . ($recent['avg_buy'] !== null
			? $this->format_credits($recent['avg_buy']) . $this->format_trend($recent['avg_buy'], $prior['avg_buy'] ?? null)
			: "no QL" . $anchorQl . " buy orders observed") . "\n";

		$range = $this->observed_range($aoid, $now - (7 * 86400), $now);
		if ($range['min_sell'] !== null) {
			$out .= "Lowest sell seen (any QL) : " . $this->format_credits($range['min_sell']) . "\n";
		}
		if ($range['max_buy'] !== null) {
			$out .= "Highest buy seen (any QL): " . $this->format_credits($range['max_buy']) . "\n";
		}

		$out .= "Snapshots taken: " . $recent['count'] . "\n";
		return $out;
	}

	/*
	min_sell_price/max_buy_price already capture the all-QL extremes each snapshot (unlike
	avg_sell_price/avg_buy_price, which are QL-anchored) - this just rolls them up over the window.
	*/
	function observed_range($aoid, $since, $until)
	{
		$base = " FROM #___market_history WHERE aoid = " . intval($aoid) . " AND ts >= " . intval($since) . " AND ts < " . intval($until);
		$sell = $this->bot->db->select("SELECT MIN(min_sell_price)" . $base . " AND sell_count > 0");
		$buy = $this->bot->db->select("SELECT MAX(max_buy_price)" . $base . " AND buy_count > 0");
		return array(
			'min_sell' => (!empty($sell) && $sell[0][0] !== null) ? (float) $sell[0][0] : null,
			'max_buy' => (!empty($buy) && $buy[0][0] !== null) ? (float) $buy[0][0] : null
		);
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
		return " (" . $sign . round($change, 1) . "% vs prior 7 days)";
	}

	/*
	Live-only (not tracked historically): buckets the current orders into 50-QL bands and shows
	avg price + price/QL per band, since a single AOID's orders can span very different QLs and
	price rarely scales linearly across the whole range. A buy order's min_ql/max_ql range can span
	multiple bands - it's counted in every band it touches, since it's a genuinely valid offer at
	any QL in that range.
	*/
	function render_ql_breakdown($orders)
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

		if (empty($buckets)) {
			return "";
		}
		ksort($buckets);

		$out = "__________Price by QL Band_________\n";
		$out .= $this->tab("QL BAND", 10) . " " . $this->tab("AVG SELL", 12) . " " . $this->tab("AVG BUY", 12)
			. " " . $this->tab("SELL/QL", 10) . " " . $this->tab("BUY/QL", 10) . "\n";
		foreach ($buckets as $band => $data) {
			$lowQl = $band * $bandSize + 1;
			$highQl = $lowQl + $bandSize - 1;
			$midQl = ($lowQl + $highQl) / 2;
			$avgSell = !empty($data['sell']) ? array_sum($data['sell']) / count($data['sell']) : null;
			$avgBuy = !empty($data['buy']) ? array_sum($data['buy']) / count($data['buy']) : null;
			$out .= $this->tab("QL" . $lowQl . "-" . $highQl, 10) . " "
				. $this->tab($avgSell !== null ? $this->format_credits($avgSell) : "-", 12) . " "
				. $this->tab($avgBuy !== null ? $this->format_credits($avgBuy) : "-", 12) . " "
				. $this->tab($avgSell !== null ? $this->format_credits($avgSell / $midQl) : "-", 10) . " "
				. $this->tab($avgBuy !== null ? $this->format_credits($avgBuy / $midQl) : "-", 10) . "\n";
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
		$content = $this->bot->core("tools")->get_site($url);
		if ($content instanceof BotError) {
			return false;
		}
		$data = json_decode($content);
		if (!is_object($data) || (!isset($data->buy_orders) && !isset($data->sell_orders))) {
			return false;
		}
		if (!isset($data->buy_orders)) {
			$data->buy_orders = array();
		}
		if (!isset($data->sell_orders)) {
			$data->sell_orders = array();
		}
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

		// Prune old history snapshots.
		$this->bot->db->query("DELETE FROM #___market_history WHERE ts < " . ($now - $retentionSeconds));

		// Re-poll the items most overdue for a refresh.
		$due = $this->bot->db->select(
			"SELECT aoid, ql FROM #___market_watch WHERE last_polled < " . ($now - $intervalSeconds)
			. " ORDER BY last_polled ASC LIMIT " . $batchSize
		);
		foreach ($due as $row) {
			$aoid = intval($row[0]);
			$anchorQl = intval($row[1]);
			$orders = $this->fetch_orders($aoid);
			if ($orders !== false) {
				$this->snapshot($aoid, $orders, $anchorQl);
			}
			$this->bot->db->query("UPDATE #___market_watch SET last_polled = " . $now . " WHERE aoid = " . $aoid);
		}
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

		$aoids = array();
		$pagesFetched = 0;
		for ($page = 1; $page <= $pages; $page++) {
			$content = $this->bot->core("tools")->get_site($sourceUrl . "/items/" . $page);
			if ($content instanceof BotError) {
				break;
			}
			if (!preg_match_all('/class="item-name"\s+href="\/item\/([0-9]+)"/i', $content, $matches)) {
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
			$this->bot->log("MARKET", "AUTOTRACK", "Could not fetch item ranking from " . $sourceUrl . ", skipping this cycle.");
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

		$rows = $this->bot->db->select(
			"SELECT aoid, name, ql, icon, auto_tracked, first_seen, last_polled FROM #___market_watch"
			. " ORDER BY auto_tracked DESC, last_polled DESC LIMIT 500"
		);
		if (empty($rows)) {
			$out .= "No items are currently tracked.\n";
			return $this->bot->core("tools")->make_blob("Market Status", $out);
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

		$out .= count($rows) . " tracked item(s) :\n\n" . $inside;
		return $this->bot->core("tools")->make_blob("Market Status", $out);
	}
}
?>
