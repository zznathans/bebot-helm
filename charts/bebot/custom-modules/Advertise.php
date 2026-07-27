<?php
/*
* Advertise.php - Periodic bot self-advertisement broadcast to a public OOC channel.
*
* Custom module for BeBot (https://github.com/J-Soft/BeBot), dropped into Custom/Modules/.
*
* Mirrors Modules/Ao/Recruit.php's existing SpamPublic/WhatChan/custom-text-file pattern for
* broadcasting into a faction OOC channel, but off by default, targeting a single configurable
* channel, on a much lower default cadence, and with copy that points somewhere useful (!market
* help) rather than being pure noise - a bare bot self-ad is pure self-promotion, unlike guild
* recruitment, which at least has some in-context value to newbies browsing for a guild.
*/

$advertise_core = new Advertise($bot);

class Advertise extends BaseActiveModule
{
	function __construct(&$bot)
	{
		parent::__construct($bot, get_class($this));
		$this->register_command("all", "advertise", "ADMIN");
		$this->help['description'] = "Periodically broadcasts a short bot self-ad to a public OOC channel.";
		$this->help['command']['advertise now'] = "Send the advertisement immediately, regardless of the Enabled setting or timer";
		$this->help['command']['advertise preview'] = "Tell yourself the advertisement so you can see how it looks, without posting it anywhere public";

		$this->bot->core("settings")
			->create("Advertise", "Enabled", false, "Should the bot periodically broadcast a self-ad to a public OOC channel ?", "On;Off");
		$this->bot->core("settings")
			->create("Advertise", "Channel", "Newbie", "Which public OOC channel should the ad be broadcast to ?", "Newbie;Neutral;Clan;Omni");
		$this->bot->core("settings")
			->create("Advertise", "IntervalMinutes", 360, "How often (in minutes) should the ad be broadcast ?");

		$this->bot->core("timer")->register_callback("Advertise", $this);
		$existing = $this->bot->core("timer")->list_timed_events("Advertise");
		$scheduled = array();
		foreach ($existing as $timer) {
			$scheduled[] = $timer['name'];
		}
		if (!in_array("Advertise-Broadcast", $scheduled)) {
			$interval = 60 * intval($this->bot->core("settings")->get("Advertise", "IntervalMinutes"));
			if ($interval < 60) {
				$interval = 60;
			}
			$this->bot->core("timer")->add_timer(true, "Advertise", $interval, "Advertise-Broadcast", "internal", $interval, "None");
		}
	}

	function command_handler($name, $msg, $channel)
	{
		if (preg_match('/^advertise\s+preview\s*$/i', $msg)) {
			$this->bot->send_tell($name, $this->message());
			return "Sent you a tell with the current advertisement text.";
		} elseif (preg_match('/^advertise\s+now\s*$/i', $msg)) {
			$this->broadcast(true);
			return "Advertisement sent.";
		}
		return "Usage: advertise preview  or  advertise now";
	}

	function timer($name, $prefix, $suffix, $delay)
	{
		if ($name == "Advertise-Broadcast") {
			$this->broadcast();
		}
	}

	/*
	$force lets `!advertise now` bypass the Enabled toggle (useful for previewing copy) without
	affecting the scheduled timer, which always still checks Enabled on its own.
	*/
	function broadcast($force = false)
	{
		if (!$force && !$this->bot->core("settings")->get("Advertise", "Enabled")) {
			return;
		}

		switch ($this->bot->core("settings")->get("Advertise", "Channel")) {
			case "Neutral":
				$channelName = "Neu. OOC";
				break;
			case "Omni":
				$channelName = "OT OOC";
				break;
			case "Clan":
				$channelName = "Clan OOC";
				break;
			default:
				$channelName = "Neu. Newbie OOC";
				break;
		}

		$msg = $this->message();
		$this->bot->aoc->send_group($channelName, $msg);
		$this->bot->log("ADVERTISE", "BROADCAST", "Sent self-ad to " . $channelName, true);
	}

	/*
	Same custom-text-file fallback order as Modules/Ao/Recruit.php's cron(), so an operator can
	customize the copy without touching code: a bot-specific override first, then a shared one.

	A bare chatcmd() link posted directly to a channel/tell does NOT render as clickable - every
	working example in the codebase (Modules/Raffle.php's click_join(), Modules/AltsUi.php's alt
	confirmation tell) always wraps it in make_blob() first. make_blob() turns its entire title
	argument into the clickable link, so the descriptive pitch is kept as plain text and only a
	short "click here" label is passed as the blob's title - otherwise the whole sentence reads
	as one giant link.
	*/
	function message()
	{
		if (file_exists("./Text/" . $this->bot->botname . "Advertise.txt")) {
			return implode("", file("./Text/" . $this->bot->botname . "Advertise.txt"));
		}
		if (file_exists("./Text/Advertise.txt")) {
			return implode("", file("./Text/Advertise.txt"));
		}
		$tools = $this->bot->core("tools");
		$teaser = $this->bot->botname . " tracks GMI market prices and can tell you the moment a new buy/sell order is posted for an item you're watching.";
		$inside = $this->bot->botname . "'s Market module lets you:\n"
			. "- Search live GMI prices for any item\n"
			. "- Track price history and trends over time\n"
			. "- Build a personal watchlist and get a tell when a new order shows up\n\n"
			. "[" . $tools->chatcmd("market help", "market help") . "]";
		return $teaser . " " . $tools->make_blob("click here", $inside);
	}
}
?>
