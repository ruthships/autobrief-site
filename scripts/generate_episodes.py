#!/usr/bin/env python3
"""Generate episode pages and listings from newsletter HTML + local audio.

Public-site variant: outputs into ./public (the Cloudflare assets directory),
reads audio from ./public/episodes, and omits the internal Documentation page.
"""

import re
import os
from html import escape, unescape
from typing import Optional
from urllib.parse import quote
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_WEBSITE_DIR = os.path.join(ROOT, "public")
NEWSLETTERS_DIR = os.path.join(ROOT, "newsletters")
EPISODES_DIR = os.path.join(ROOT, "public", "episodes")

# Legacy newsletter filenames that don't follow episode-N naming (none currently)
NEWSLETTER_OVERRIDES: dict[int, str] = {}

GITHUB_ASSETS = "https://raw.githubusercontent.com/ruthships/ai-podcast/main/assets"
AUDIO_PATTERN = re.compile(
    r"Episode (\d+) - ([A-Za-z]+ \d{1,2} \d{4})\.(mp3|m4a)$"
)


def strip_tags(html: str) -> str:
    text = re.sub(r"<[^>]+>", "", html)
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_image(src: str, ep: int) -> str:
    if src.startswith("http"):
        return src
    name = os.path.basename(src)
    if name.startswith("ep") or name.startswith("1_"):
        return f"{GITHUB_ASSETS}/{name}"
    return f"{GITHUB_ASSETS}/ep{ep}_hero.jpg"


def discover_audio_files() -> dict[int, str]:
    files = {}
    for name in os.listdir(EPISODES_DIR):
        if name.startswith(".") or os.path.isdir(os.path.join(EPISODES_DIR, name)):
            continue
        match = AUDIO_PATTERN.search(name)
        if match:
            files[int(match.group(1))] = name
    return files


def discover_newsletters() -> dict[int, str]:
    mapping = dict(NEWSLETTER_OVERRIDES)
    for name in os.listdir(NEWSLETTERS_DIR):
        match = re.search(r"episode-(\d+)", name, re.I)
        if match:
            mapping[int(match.group(1))] = name
    return mapping


def audio_duration(path: str) -> str:
    import subprocess

    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                path,
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        seconds = int(float(result.stdout.strip()))
        return f"{seconds // 60}:{seconds % 60:02d}"
    except (FileNotFoundError, subprocess.CalledProcessError, ValueError):
        return ""


def parse_newsletter_html(path: str, ep: int) -> dict:
    html = open(path, encoding="utf-8").read()

    date_match = re.search(
        r'heading_block block-2"[^>]*>.*?<h1[^>]*>([^<]+)</h1>', html, re.S
    )
    date_display = date_match.group(1).strip() if date_match else ""
    date_iso = datetime.strptime(date_display, "%B %d, %Y").strftime("%Y-%m-%d")

    summary_match = re.search(
        r'paragraph_block block-3".*?<p style="margin: 0;">(.*?)</p>', html, re.S
    )
    summary = strip_tags(summary_match.group(1)) if summary_match else ""

    hero_match = re.search(r"row-2.*?src=\"([^\"]+)\".*?alt=\"([^\"]+)\"", html, re.S)
    hero_image = normalize_image(hero_match.group(1), ep) if hero_match else ""

    # Episode title (theme) is decoupled from the hero image's alt text. The alt
    # is for accessibility / the image's literal content (e.g. "financial district
    # skyline") and makes a poor page heading. /podcast-email writes the editorial
    # theme into an explicit marker; prefer that. Fall back to the old hero-alt
    # behavior only for legacy newsletters that predate the marker.
    theme_marker = re.search(r"<!--\s*EPISODE_THEME:\s*(.*?)\s*-->", html, re.S)
    if theme_marker and theme_marker.group(1).strip():
        theme = theme_marker.group(1).strip()
    else:
        theme = hero_match.group(2).strip() if hero_match else f"Episode {ep}"

    sections = []
    story_html = html.split("<!-- HEADLINE", 1)[-1] if "<!-- HEADLINE" in html else html
    for block in re.finditer(
        r"heading_block block-1.*?<h3[^>]*>(.*?)</h3>.*?paragraph_block block-2.*?<p style=\"margin: 0;\">(.*?)</p>",
        story_html,
        re.S,
    ):
        title = strip_tags(block.group(1))
        body = strip_tags(block.group(2))
        if title and body:
            sections.append({"title": title, "body": body})

    # Last-resort cleanup only when we fell back to the hero alt (no explicit
    # marker) and that alt looks like a generic label rather than a real theme.
    if not theme_marker and summary and (len(theme) < 20 or theme.lower().startswith("connected")):
        first_sentence = re.split(r"(?<=[.!?])\s+", summary)[0]
        theme = first_sentence[:100] + ("…" if len(first_sentence) > 100 else "")

    return {
        "date_display": date_display,
        "date_iso": date_iso,
        "theme": theme,
        "summary": summary,
        "sections": sections,
        "hero_image": hero_image or f"{GITHUB_ASSETS}/ep{ep}_hero.jpg",
    }


def build_episode(ep: int, audio_file: str, newsletter_file: Optional[str]) -> dict:
    date_match = re.search(r"Episode \d+ - (.+)\.(mp3|m4a)$", audio_file)
    date_from_audio = date_match.group(1) if date_match else ""
    date_iso = datetime.strptime(date_from_audio, "%B %d %Y").strftime("%Y-%m-%d")
    date_display = datetime.strptime(date_from_audio, "%B %d %Y").strftime("%B %d, %Y")

    audio_path = os.path.join(EPISODES_DIR, audio_file)
    audio_url = "episodes/" + quote(audio_file)
    mime = "audio/mp4" if audio_file.endswith(".m4a") else "audio/mpeg"
    duration = audio_duration(audio_path)

    if newsletter_file:
        meta = parse_newsletter_html(
            os.path.join(NEWSLETTERS_DIR, newsletter_file), ep
        )
    else:
        meta = {
            "date_display": date_display,
            "date_iso": date_iso,
            "theme": f"Weekly AI briefing — {date_display}",
            "summary": (
                "Weekly AI news briefing for C-suite leaders — headlines scraped, "
                "script generated, decisions informed. Full show notes coming soon."
            ),
            "sections": [],
            "hero_image": "tmp/sample-header1.jpg",
        }

    summary = meta["summary"]
    return {
        "number": ep,
        "slug": f"episode-{ep}.html",
        "date_display": meta["date_display"] or date_display,
        "date_iso": meta["date_iso"] or date_iso,
        "theme": meta["theme"],
        "summary": summary,
        "sections": meta["sections"],
        "hero_image": meta["hero_image"],
        "audio_url": audio_url,
        "audio_mime": mime,
        "duration": duration,
        "excerpt": summary[:220] + ("…" if len(summary) > 220 else ""),
    }


def header(active: str = "") -> str:
    about_current = ' current-menu-item' if active == "about" else ""
    episodes_current = (
        ' current-menu-item current-menu-parent' if active == "episodes" else ""
    )
    return f"""	<header id="top" class="navbar navbar-sticky">
		<div class="container">
			<div class="row align-items-center">
				<div class="site-title col col-lg-auto order-first">
					<div class="site-branding">
						<h1 class="text"><a href="index.html">AutoBrief</a></h1>
						<p class="site-tagline">AI-generated weekly podcast</p>
					</div>
				</div>
				<nav id="site-menu" class="col-12 col-lg order-3 order-sm-4 order-lg-2">
					<ul>
						<li class="menu-item{about_current}"><a href="about.html">About</a></li>
						<li class="menu-item menu-item-has-children{episodes_current}">
							<a href="episodes.html">Episodes</a>
							<a href="#" class="menu-expand"></a>
							<ul class="sub-menu">
								<li class="menu-item"><a href="episodes.html">Browse Episodes</a></li>
							</ul>
						</li>
					</ul>
				</nav>
				<div class="site-menu-toggle col-auto order-2 order-sm-3">
					<a href="#site-menu">
						<span class="screen-reader-text">Toggle navigation</span>
					</a>
				</div>
			</div>
		</div>
	</header>"""


def footer() -> str:
    return """	<footer id="footer" class="padding-top-bottom">
		<div class="container">
			<div class="row">
				<div class="widget-area col-12">
					<section class="widget widget_text">
						<h3 class="widget-title">Subscribe</h3>
						<div class="textwidget">
							<p>AutoBrief: your AI-written weekly on AI. Headlines in, script out, decisions informed.</p>
							<p class="subscribe-coming-soon">Email subscriptions coming soon.</p>
						</div>
					</section>
				</div>
				<div class="copyright col-12">
					<p>&copy; AutoBrief. AI-written weekly briefings for the C-suite. All rights reserved.</p>
				</div>
			</div>
		</div>
	</footer>

	<script src="assets/js/jquery-3.2.1.min.js"></script>
	<script src="assets/js/modernizr-custom.js"></script>
	<script src="assets/js/functions.js"></script>
	<script src="assets/js/access-gate.js"></script>

	<link rel="stylesheet" id="mediaelement-css" href="assets/mediaelement/mediaelementplayer-legacy.css">
	<link rel="stylesheet" id="wp-mediaelement-css" href="assets/mediaelement/wp-mediaelement.css">
	<link rel="stylesheet" id="castilo-additional-mediaelement-css" href="assets/css/mediaelement-castilo.css">
	<script src="assets/mediaelement/mediaelement-and-player.js"></script>
	<script src="assets/mediaelement/mediaelement-migrate.js"></script>
	<script src="assets/mediaelement/wp-mediaelement.js"></script>
	<script src="assets/js/mediaelement-castilo.js"></script>
</body>
</html>"""


def head(title: str, description: str, hero_image: str = "") -> str:
    inline = ""
    if hero_image:
        inline = f"""
	<style id="castilo-inline-style">
		.featured-content {{
			background-color: #121212;
			background-image: url({hero_image});
		}}
	</style>"""
    return f"""<!doctype html>
<html lang="en" class="no-js">
<head>
	<title>{escape(title)}</title>
	<meta charset="utf-8">
	<meta name="viewport" content="width=device-width, initial-scale=1, shrink-to-fit=no">
	<meta name="description" content="{escape(description)}">
	<meta name="keywords" content="AutoBrief, AI podcast, C-suite, executive briefing, artificial intelligence news">
	<link href="https://fonts.googleapis.com/css?family=Oswald:300,400%7CKarla:400,700" rel="stylesheet">
	<link rel="shortcut icon" href="favicon.png">
	<link rel="stylesheet" href="assets/css/bootstrap-reboot.css">
	<link rel="stylesheet" href="assets/css/bootstrap-grid.css">
	<link rel="stylesheet" href="assets/css/material-design-iconic-font.css">
	<link rel="stylesheet" href="assets/css/style.css">
	<link rel="stylesheet" href="assets/css/style-custom.css">{inline}
</head>"""


def audio_player(ep: dict, featured: bool = False) -> str:
    return f"""							<div class="podcast-episode-player" data-episode-duration="{ep['duration']}">
								<audio class="wp-audio-shortcode" preload="none" style="width: 100%;" controls="controls">
									<source src="{ep['audio_url']}" type="{ep['audio_mime']}" />
								</audio>
							</div>"""


def listing_card(ep: dict, image_class: int) -> str:
    img = ep["hero_image"] or f"tmp/sample-post-square{image_class % 3 + 1}.jpg"
    return f"""						<article class="entry entry-episode">
							<div class="row align-items-lg-center">
								<div class="col-12 col-md-4 col-xl-3">
									<div class="entry-media entry-image multiply-effect">
										<a href="{ep['slug']}">
											<img class="first" src="{img}" width="736" height="736" alt="{escape(ep['theme'])}">
											<span class="second"><img src="{img}" width="736" height="736" alt=""></span>
											<span class="third"><img src="{img}" width="736" height="736" alt=""></span>
										</a>
									</div>
								</div>
								<div class="col-12 col-md-8 col-xl-9">
									<header class="entry-header">
										<div class="entry-meta">
											<span class="posted-on"><span class="screen-reader-text">Posted on: </span> <a href="{ep['slug']}" rel="bookmark"><time class="entry-date published" datetime="{ep['date_iso']}">{ep['date_display']}</time></a></span>
											<span class="tags"><span class="screen-reader-text">Episode: </span> <a rel="tag" href="{ep['slug']}">Episode {ep['number']}</a></span>
										</div>
										<h2 class="entry-title"><a href="{ep['slug']}" rel="bookmark">{escape(ep['theme'])}</a></h2>
									</header>
									<div class="entry-content">
										<p>{escape(ep['excerpt'])} <a href="{ep['slug']}">(read more)</a></p>
									</div>
									<div class="entry-audio">
										<div class="podcast-episode">
											{audio_player(ep)}
										</div>
									</div>
								</div>
							</div>
						</article>"""


def render_episode_page(ep: dict, prev_ep: Optional[dict], next_ep: Optional[dict]) -> str:
    sections_html = "\n".join(
        f"							<h3>{escape(s['title'])}</h3>\n							<p>{escape(s['body'])}</p>"
        for s in ep["sections"]
    )
    nav_html = ""
    if prev_ep or next_ep:
        prev_block = (
            f"""									<div class="prev-post col-12 col-lg-6">
										<a href="{prev_ep['slug']}" rel="prev"><span class="zmdi zmdi-long-arrow-left"></span> Prev</a>
										<h5><a href="{prev_ep['slug']}">Episode {prev_ep['number']}: {escape(prev_ep['theme'])}</a></h5>
									</div>"""
            if prev_ep
            else ""
        )
        next_block = (
            f"""									<div class="next-post col-12 col-lg-6 offset-lg-0">
										<a href="{next_ep['slug']}" rel="next">Next <span class="zmdi zmdi-long-arrow-right"></span></a>
										<h5><a href="{next_ep['slug']}">Episode {next_ep['number']}: {escape(next_ep['theme'])}</a></h5>
									</div>"""
            if next_ep
            else ""
        )
        nav_html = f"""
						<div class="entry-footer">
							<aside class="post-controls">
								<div class="row">
{prev_block}
{next_block}
								</div>
							</aside>
						</div>"""

    return (
        head(
            f"Episode {ep['number']} — {ep['date_display']} — AutoBrief",
            ep["summary"][:160],
            ep["hero_image"],
        )
        + f"""
<body class="single-episode">
{header("episodes")}

	<header id="featured" class="featured-content fade-background-60 padding-top-bottom">
		<div class="container">
			<div class="row align-items-center">
				<div class="col-12 col-lg-8 col-xl-7">
					<p class="big text-uppercase opacity-50">Episode {ep['number']}</p>
					<h1 class="entry-title">{escape(ep['theme'])}</h1>
					<div class="entry-meta">
						<span class="posted-on"><time class="entry-date published" datetime="{ep['date_iso']}">{ep['date_display']}</time></span>
					</div>
					<div class="podcast-episode">
						{audio_player(ep, featured=True)}
					</div>
				</div>
			</div>
		</div>
	</header>

	<main id="content" class="padding-top-bottom">
		<div class="container">
			<div class="row">
				<div class="col-12 col-lg-10">
					<article class="entry entry-episode">
						<div class="entry-content">
							<p>{escape(ep['summary'])}</p>
{sections_html}
						</div>{nav_html}
					</article>
				</div>
			</div>
		</div>
	</main>

{footer()}"""
    )


def render_index(latest: dict, episodes: list[dict]) -> str:
    listing = "\n".join(listing_card(ep, i) for i, ep in enumerate(episodes))
    hero_img = latest["hero_image"]
    inline = f"""
	<style id="castilo-inline-style">
		.featured-content {{
			background-color: #121212;
			background-image: url({hero_img});
		}}
	</style>"""
    return f"""<!doctype html>
<html lang="en" class="no-js">
<head>
	<title>AutoBrief — AI Weekly Briefing for Leaders</title>
	<meta charset="utf-8">
	<meta name="viewport" content="width=device-width, initial-scale=1, shrink-to-fit=no">
	<meta name="description" content="AutoBrief — your AI-written weekly briefing on AI news for C-suite leaders. Headlines scraped, script generated, decisions informed.">
	<meta name="keywords" content="AutoBrief, AI podcast, C-suite, executive briefing, artificial intelligence news">
	<link href="https://fonts.googleapis.com/css?family=Oswald:300,400%7CKarla:400,700" rel="stylesheet">
	<link rel="shortcut icon" href="favicon.png">
	<link rel="stylesheet" href="assets/css/bootstrap-reboot.css">
	<link rel="stylesheet" href="assets/css/bootstrap-grid.css">
	<link rel="stylesheet" href="assets/css/material-design-iconic-font.css">
	<link rel="stylesheet" href="assets/css/style.css">
	<link rel="stylesheet" href="assets/css/style-custom.css">{inline}
</head>
<body class="home">
{header()}

	<header id="featured" class="featured-content fade-background-0 padding-top-bottom">
		<div class="container">
			<div class="row align-items-center">
				<div class="col-12 col-lg-8 col-xl-7">
					<div class="latest-episode">
						<div class="podcast-episode">
							<p class="big text-uppercase opacity-50">This Week's Brief · Episode {latest['number']}</p>
							<h1 class="entry-title"><a href="{latest['slug']}">{escape(latest['theme'])}</a></h1>
							<div class="podcast-episode">
								{audio_player(latest, featured=True)}
							</div>
							<p><a href="{latest['slug']}" class="button button-filled button-color">Read briefing</a></p>
						</div>
					</div>
				</div>
			</div>
		</div>
	</header>

	<main id="content" class="padding-top-bottom">
		<div class="container">
			<div class="row">
				<div class="col-12">
					<div class="episodes-listing">
						<h3 class="add-separator"><span>Recent <em>Briefings</em></span></h3>
{listing}
					</div>
				</div>
			</div>
		</div>
	</main>

{footer()}"""


def render_episodes_page(episodes: list[dict]) -> str:
    listing = "\n".join(listing_card(ep, i) for i, ep in enumerate(episodes))
    return (
        head("Episodes — AutoBrief", "Browse all AutoBrief weekly AI briefings for C-suite leaders.")
        + f"""
<body>
{header("episodes")}

	<header id="featured" class="featured-content fade-background-50 padding-top-bottom">
		<div class="container">
			<div class="row align-items-center">
				<div class="col-12 col-md">
					<h1 class="entry-title">All Briefings</h1>
				</div>
			</div>
		</div>
	</header>

	<main id="content" class="padding-top-bottom">
		<div class="container">
			<div class="row">
				<div class="col-12">
					<div class="episodes-listing">
{listing}
					</div>
				</div>
			</div>
		</div>
	</main>

{footer()}"""
    )


def main():
    audio_files = discover_audio_files()
    newsletters = discover_newsletters()

    episodes = [
        build_episode(ep, audio_files[ep], newsletters.get(ep))
        for ep in sorted(audio_files.keys(), reverse=True)
    ]
    by_num = {ep["number"]: ep for ep in episodes}

    for ep in episodes:
        n = ep["number"]
        prev_ep = by_num.get(n - 1)
        next_ep = by_num.get(n + 1)
        out = os.path.join(STATIC_WEBSITE_DIR, ep["slug"])
        with open(out, "w", encoding="utf-8") as f:
            f.write(render_episode_page(ep, prev_ep, next_ep))
        print(f"Wrote {out}")

    with open(os.path.join(STATIC_WEBSITE_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(render_index(episodes[0], episodes))

    with open(os.path.join(STATIC_WEBSITE_DIR, "episodes.html"), "w", encoding="utf-8") as f:
        f.write(render_episodes_page(episodes))

    print(f"Updated index.html and episodes.html ({len(episodes)} episodes)")


if __name__ == "__main__":
    main()
