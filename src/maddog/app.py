import click
import pathlib
import datetime
import re
from dateutil import parser
from rich.table import Table
from rich.console import Console

console = Console()
now = datetime.datetime.now()

ALL_TODO_RE = re.compile(
    r"""^
    (?:\s*-\s*)?
    (TODO|IDEA|DONE):?     # label starts a line
    \s*([^\{\n]+)           # body ends at { or newline
    (?:\s*(\{.*\}))?         # repeated variations of {...} tags
    """,
    re.VERBOSE,
)
CHECKBOX_RE = re.compile(r"\s*-\s*\[([ x]?)\]\s*(.*)")
TAG_SPLIT_RE = re.compile(r"\{([^:]+):([^}]+)\}")
TODO_TODO_RE = re.compile(r"^(TODO):?\s*")


def parse_todo_tag(tag, val) -> tuple[str, str]:
    """
    return tag, style_override
    """
    if tag == "by":
        dval = parser.parse(val)
        days_left = dval - now
        style = "red" if days_left.days <= 0 else "yellow"
        return f"by {dval.date()} ({days_left.days})", style
    else:
        return f"{tag}:{val}", ""


def scan_contents(file: pathlib.Path) -> dict:
    text = file.read_text()
    words = text.split()
    return {"words": len(words), "todos": len(TODO_TODO_RE.findall(text))}


def pull_todos(file: pathlib.Path):
    text = file.read_text().splitlines()
    active_todo = None
    for line in text:
        todo = ALL_TODO_RE.match(line)
        if todo:
            if active_todo:
                yield active_todo
            tag_strs = []
            style = ""
            status, description, tags = todo.groups()
            if tags:
                for tag, val in TAG_SPLIT_RE.findall(tags):
                    ts, style = parse_todo_tag(tag, val)
                    tag_strs.append(ts)
            if status == "DONE":
                style = "#999999"
            elif status == "IDEA":
                style = "blue"
            active_todo = {
                "file": file.name,
                "status": status,
                "description": description,
                "tags": " | ".join(tag_strs),
                "style": style,
                "subtasks": [],
            }
        elif active_todo:
            # check for checkbox if we're nested inside a todo
            checkbox = CHECKBOX_RE.match(line)
            if checkbox:
                checkbox_status, desc = checkbox.groups()
                active_todo["subtasks"].append(
                    {"status": checkbox_status, "description": desc}
                )
            else:
                yield active_todo
                active_todo = None

    # make sure to yield final line if needed
    if active_todo:
        yield active_todo


def human_readable_date(dt: datetime.datetime) -> str:
    delta = now - dt
    if delta < datetime.timedelta(hours=1):
        return f"{int(delta.total_seconds() / 60)}m ago"
    elif delta < datetime.timedelta(days=1):
        return f"{int(delta.total_seconds() / 3600)}h ago"
    else:
        return f"{int(delta.total_seconds() / 3600 / 24)}d ago"


def lod_table(data: list[dict]) -> Table | str:
    """list of dicts to Table"""
    if not data:
        return "no results"

    table = Table()
    for key in data[0].keys():
        if key != "style":
            table.add_column(key)

    for row in data:
        style = row.pop("style", None)
        table.add_row(*(str(x) for x in row.values()), style=style)

    return table


@click.group()
def cli():
    pass


def get_files(dirname):
    if not dirname:
        dirname = "~/wiki/"
    p = pathlib.Path(dirname[0]).expanduser()
    return p.rglob("*.md")


@cli.command()
@click.argument("dirname", nargs=-1)
def todos(dirname):
    output = []  # list of data
    for file in get_files(dirname):
        output += pull_todos(file)
    table = lod_table(output)
    console.print(table)


@cli.command()
@click.argument("dirname", nargs=-1)
def ls(dirname):
    table = Table()
    output = []
    for file in get_files(dirname):
        st = file.stat()
        modified = datetime.datetime.fromtimestamp(st.st_mtime)
        scan = scan_contents(file)
        output.append(
            {
                "file": file.name,
                "modified": human_readable_date(modified),
                **scan,
                "style": "yellow" if scan["todos"] else "white",
            }
        )
    table = lod_table(output)
    console.print(table)


if __name__ == "__main__":
    cli()
