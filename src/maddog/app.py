import click
import pathlib
import datetime
import re
from dateutil import parser
from rich.table import Table
from rich.console import Console

console = Console()
now = datetime.datetime.now()

ALL_TODO_RE = re.compile(r"^(TODO|IDEA|DONE):?\s*([^\{\n]+)(\{.*\})?", re.MULTILINE)
TODO_TODO_RE = re.compile(r"(TODO):?\s*")


def parse_todo_tag(tag) -> tuple[str, str]:
    """
    return tag, style_override
    """
    if not tag:
        return "", ""
    name, val = tag.strip("{}").split(":", 1)
    if name == "by":
        dval = parser.parse(val)
        days_left = dval - now
        style = "red" if days_left.days <= 0 else ""
        return f"by {dval.date()} ({days_left.days})", style
    else:
        return f"{name}:{val}", ""


def scan_contents(file: pathlib.Path) -> dict:
    text = file.read_text()
    words = text.split()
    return {"words": len(words), "todos": len(TODO_TODO_RE.findall(text))}


def pull_todos(file: pathlib.Path):
    text = file.read_text()
    todos = ALL_TODO_RE.findall(text)
    for t in todos:
        style = {"TODO": "yellow", "DONE": "#999999"}[t[0]]
        tags, style_override = parse_todo_tag(t[2])
        yield {
            "file": file.name,
            "status": t[0],
            "description": t[1],
            "tags": tags,
            "style": style_override or style,
        }


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
    p = pathlib.Path(dirname).expanduser()
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
