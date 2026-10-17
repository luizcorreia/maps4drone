"""Create (or update) the maps4drone theme in a WebODM, and optionally make it the active one.

The theme is webodm_theme/maps4drone.json (colours) plus maps4drone.css, which paint WebODM
with the same palette as the planner. Run it with an administrator account:

    python scripts/install_webodm_theme.py --url http://localhost:8000 --user admin
    python scripts/install_webodm_theme.py ... --activate      # also select it
    python scripts/install_webodm_theme.py ... --activate-theme Default   # go back

The password is read from WEBODM_PASSWORD, or asked for.
"""

import argparse
import getpass
import http.cookiejar
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

THEME_DIR = Path(__file__).resolve().parents[1] / "webodm_theme"
HEX = re.compile(r"^#([0-9a-fA-F]{6})$")


class FormReader(HTMLParser):
    """Collects the fields of the page's first <form> that has a given action, with their values."""

    def __init__(self) -> None:
        super().__init__()
        self.fields: dict[str, str] = {}
        self.options: dict[str, list[tuple[str, str]]] = {}
        self._select: str | None = None
        self._textarea: str | None = None
        self._option: str | None = None
        self._selected: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k: v or "" for k, v in attrs}
        name = a.get("name")
        if tag == "input" and name:
            kind = a.get("type", "text")
            if kind in ("checkbox", "radio") and "checked" not in a:
                return
            if kind in ("submit", "button", "file"):
                return
            self.fields[name] = a.get("value", "on" if kind == "checkbox" else "")
        elif tag == "select" and name:
            self._select = name
            self.options[name] = []
        elif tag == "option" and self._select:
            value = a.get("value", "")
            self._option = value
            self.options[self._select].append((value, ""))
            if "selected" in a:
                self._selected[self._select] = value
        elif tag == "textarea" and name:
            self._textarea = name
            self.fields[name] = ""

    def handle_endtag(self, tag: str) -> None:
        if tag == "select":
            if self._select and self._select in self._selected:
                self.fields[self._select] = self._selected[self._select]
            elif self._select and self.options.get(self._select):
                self.fields[self._select] = self.options[self._select][0][0]
            self._select = None
        elif tag == "textarea":
            self._textarea = None
        elif tag == "option":
            self._option = None

    def handle_data(self, data: str) -> None:
        if self._textarea:
            self.fields[self._textarea] += data
        elif self._option is not None and self._select and self.options[self._select]:
            value, label = self.options[self._select][-1]
            self.options[self._select][-1] = (value, label + data.strip())


class Admin:
    def __init__(self, url: str, user: str, password: str) -> None:
        self.url = url.rstrip("/")
        self.jar = http.cookiejar.CookieJar()
        self.http = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
        self.login(user, password)

    def _cookie(self, name: str) -> str:
        return next((c.value for c in self.jar if c.name == name), "")

    def get(self, path: str) -> str:
        with self.http.open(self.url + path) as resp:
            return str(resp.read().decode("utf-8"))

    def post(self, path: str, fields: dict[str, str]) -> str:
        data = urllib.parse.urlencode({**fields, "csrfmiddlewaretoken": self._cookie("csrftoken")})
        request = urllib.request.Request(
            self.url + path, data.encode(), headers={"Referer": self.url + path}
        )
        with self.http.open(request) as resp:
            return str(resp.read().decode("utf-8"))

    def login(self, user: str, password: str) -> None:
        self.get("/login/")
        page = self.post("/login/", {"username": user, "password": password, "next": "/dashboard/"})
        if "/login/" in page and 'name="password"' in page:
            raise SystemExit("login failed: check the user and password")

    def form(self, path: str) -> FormReader:
        reader = FormReader()
        reader.feed(self.get(path))
        return reader


def theme_id(admin: Admin, name: str) -> str | None:
    """The id of the theme called `name` in the admin list, if there is one."""
    page = admin.get("/admin/app/theme/")
    for match in re.finditer(r'href="/admin/app/theme/(\d+)/change/">([^<]*)<', page):
        if match.group(2).strip() == name:
            return match.group(1)
    return None


def install(admin: Admin) -> str:
    colours = json.loads((THEME_DIR / "maps4drone.json").read_text())
    css = (THEME_DIR / "maps4drone.css").read_text()
    existing = theme_id(admin, colours["name"])
    path = f"/admin/app/theme/{existing}/change/" if existing else "/admin/app/theme/add/"
    form = admin.form(path)
    form.fields.update({**colours, "css": css})
    # the colour widget posts hex digits without the "#", and refuses a value that has it
    form.fields = {k: HEX.sub(r"\1", v) for k, v in form.fields.items()}
    form.fields["_save"] = "Save"
    admin.post(path, form.fields)
    saved = theme_id(admin, colours["name"])
    if saved is None:
        raise SystemExit("the theme was not saved: the admin form refused it")
    print(f"theme '{colours['name']}' {'updated' if existing else 'created'} (id {saved})")
    return colours["name"]


def activate(admin: Admin, name: str) -> None:
    """Select the theme called `name` in WebODM's settings."""
    path = "/admin/app/setting/1/change/"
    form = admin.form(path)
    options = {label: value for value, label in form.options.get("theme", [])}
    if name not in options:
        raise SystemExit(f"no theme called '{name}' (have: {', '.join(sorted(options))})")
    form.fields["theme"] = options[name]
    form.fields["_save"] = "Save"
    admin.post(path, form.fields)
    print(f"active theme: {name}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--url", default="http://localhost:8000")
    parser.add_argument("--user", required=True)
    parser.add_argument("--activate", action="store_true", help="select the maps4drone theme")
    parser.add_argument(
        "--activate-theme", metavar="NAME", help="select another theme, e.g. Default"
    )
    args = parser.parse_args()
    password = os.environ.get("WEBODM_PASSWORD") or getpass.getpass("WebODM password: ")
    admin = Admin(args.url, args.user, password)
    if args.activate_theme:
        activate(admin, args.activate_theme)
        return
    name = install(admin)
    if args.activate:
        activate(admin, name)


if __name__ == "__main__":
    sys.exit(main())
