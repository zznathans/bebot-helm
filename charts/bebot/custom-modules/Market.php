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

		$this->table();

		$this->bot->core("timer")->register_callback("Market", $this);
		$existing = $this->bot->core("timer")->list_timed_events("Market");
		if (empty($existing)) {
			$interval = 60 * intval($this->bot->core("settings")->get("Market", "PollIntervalMinutes"));
			if ($interval < 60) {
				$interval = 60;
			}
			$this->bot->core("timer")->add_timer(true, "Market", $interval, "Market-Poll", "internal", $interval, "None");
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
	}

	function command_handler($name, $msg, $channel)
	{
		if (preg_match('/^(?:market|mkt)\s+([0-9]+)\s*$/i', $msg, $info)) {
			return $this->show_overview($name, intval($info[1]));
		} elseif (preg_match('/^(?:market|mkt)\s+(.+)$/i', $msg, $info)) {
			return $this->search_items(trim($info[1]));
		} else {
			return "Usage: market <item name>  or  market <aoid>";
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

		$inside = "<img src=rdb://" . $icon . "> <a href='itemref://" . $id . "/" . $id . "/" . $ql . "'>" . $itemName . "</a> QL" . $ql . "\n";
		$inside .= "[" . $this->bot->core("tools")->chatcmd("items " . $itemName, "Full Item Info") . "]"
			. " [" . $this->bot->core("tools")->chatcmd("gmi " . $id . " " . $itemName, "Full Order List") . "]\n\n";

		$orders = $this->fetch_orders($id);
		if ($orders === false) {
			$inside .= "Market data currently unavailable, please try again later.\n\n";
		} else {
			$inside .= $this->render_summary($orders);
			$inside .= "\n";
			$inside .= $this->render_history($id);
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

	function render_history($aoid)
	{
		$now = time();
		$recent = $this->history_average($aoid, $now - (7 * 86400), $now);
		$prior = $this->history_average($aoid, $now - (14 * 86400), $now - (7 * 86400));

		if ($recent === null) {
			return "__________Price History_________\nPrice history tracking just started for this item - check back later.\n";
		}

		$out = "__________Price History (7 days)_________\n";
		$out .= "Avg sell price : " . $this->format_credits($recent['avg_sell']) . $this->format_trend($recent['avg_sell'], $prior['avg_sell'] ?? null) . "\n";
		$out .= "Avg buy price  : " . $this->format_credits($recent['avg_buy']) . $this->format_trend($recent['avg_buy'], $prior['avg_buy'] ?? null) . "\n";
		$out .= "Snapshots taken: " . $recent['count'] . "\n";
		return $out;
	}

	function history_average($aoid, $since, $until)
	{
		$result = $this->bot->db->select(
			"SELECT AVG(avg_sell_price), AVG(avg_buy_price), COUNT(*) FROM #___market_history"
			. " WHERE aoid = " . intval($aoid) . " AND ts >= " . intval($since) . " AND ts < " . intval($until)
		);
		if (empty($result) || $result[0][2] == 0) {
			return null;
		}
		return array(
			'avg_sell' => (float) $result[0][0],
			'avg_buy' => (float) $result[0][1],
			'count' => (int) $result[0][2]
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
		$expired = $this->bot->db->select(
			"SELECT aoid FROM #___market_watch WHERE GREATEST(last_polled, first_seen) < " . ($now - $expireSeconds)
		);
		foreach ($expired as $row) {
			$this->bot->db->query("DELETE FROM #___market_history WHERE aoid = " . intval($row[0]));
			$this->bot->db->query("DELETE FROM #___market_watch WHERE aoid = " . intval($row[0]));
		}

		// Prune old history snapshots.
		$this->bot->db->query("DELETE FROM #___market_history WHERE ts < " . ($now - $retentionSeconds));

		// Re-poll the items most overdue for a refresh.
		$due = $this->bot->db->select(
			"SELECT aoid FROM #___market_watch WHERE last_polled < " . ($now - $intervalSeconds)
			. " ORDER BY last_polled ASC LIMIT " . $batchSize
		);
		foreach ($due as $row) {
			$aoid = intval($row[0]);
			$orders = $this->fetch_orders($aoid);
			if ($orders !== false) {
				$this->snapshot($aoid, $orders);
			}
			$this->bot->db->query("UPDATE #___market_watch SET last_polled = " . $now . " WHERE aoid = " . $aoid);
		}
	}

	function snapshot($aoid, $orders)
	{
		$sellCount = count($orders->sell_orders);
		$buyCount = count($orders->buy_orders);
		$minSell = 0;
		$avgSell = 0;
		if ($sellCount > 0) {
			$prices = array_map(function ($o) {
				return $o->price;
			}, $orders->sell_orders);
			$minSell = min($prices);
			$avgSell = array_sum($prices) / $sellCount;
		}
		$maxBuy = 0;
		$avgBuy = 0;
		if ($buyCount > 0) {
			$prices = array_map(function ($o) {
				return $o->price;
			}, $orders->buy_orders);
			$maxBuy = max($prices);
			$avgBuy = array_sum($prices) / $buyCount;
		}
		$this->bot->db->query(
			"INSERT INTO #___market_history (aoid, ts, sell_count, buy_count, min_sell_price, max_buy_price, avg_sell_price, avg_buy_price) VALUES ("
				. intval($aoid) . ", " . time() . ", " . $sellCount . ", " . $buyCount . ", "
				. intval($minSell) . ", " . intval($maxBuy) . ", " . intval($avgSell) . ", " . intval($avgBuy) . ")"
		);
	}
}
?>
