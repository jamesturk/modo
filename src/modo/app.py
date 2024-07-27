import click
import pathlib
import datetime
import re
from dataclasses import dataclass
from dateutil import parser
from rich.table import Table
from rich.console import Console

console = Console()
now = datetime.datetime.now()

SORT_ORDER = ["TODO", "IDEA", "DONE"]
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
TODO_TODO_RE = re.compile(
    r"""^
    (?:\s*-\s*)?
    (TODO|IDEA|DONE):?     # label starts a line
    """,
    re.VERBOSE | re.MULTILINE,
)


def get_files(dirname):
    if not dirname:
        dirname = "."
    else:
        dirname = dirname[0]
    p = pathlib.Path(dirname).expanduser()
    return p.rglob("*.md")


def lod_table(data: list["TodoItem"]) -> Table | str:
    """list of dicts to Table"""
    if not data:
        return "no results"

    table = Table()
    for key in data[0].fields():
        table.add_column(key)

    for row in data:
        table.add_row(*row.to_row(), style=row.style)

    return table


def do_sorting(output, sort, default_sort, sort_factory):
    reverse = False
    if not sort:
        sort = default_sort
    else:
        if sort[0] == "-":
            reverse = True
            sort = sort[1:]
        sort = sort.split(",")
    sort_func = sort_factory(sort)
    output.sort(key=sort_func, reverse=reverse)


@click.group()
def cli():
    pass


# todo listing #####


@dataclass
class TodoItem:
    file: str
    status: str
    description: str
    tags: list[str]
    style: str
    subtasks: list[tuple[bool, str]]

    def fields(self):
        return [
            "file",
            "status",
            "description",
            "tags",
        ]

    def to_row(self):
        return [
            self.file,
            self.status + self.subtask_status(),
            self.description + self.subtask_nested(),
            " | ".join(self.tags),
        ]

    def status_sort(self):
        return SORT_ORDER.index(self.status)

    def due(self):
        for t in self.tags:
            if t.startswith("by"):
                return t
        return "zzzzzzz"  # sort to end

    def subtask_nested(self):
        if not self.subtasks:
            return ""
        else:
            return "\n" + "\n".join(
                f"- {render_checkbox(s[0])} {s[1]}" for s in self.subtasks
            )

    def subtask_status(self):
        total = len(self.subtasks)
        if not total:
            return ""
        done = sum(1 if st[0] else 0 for st in self.subtasks)
        return f" {done}/{total}"


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


def render_checkbox(done: bool):
    return "☑" if done else "☐"


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
            active_todo = TodoItem(
                file=file.name,
                status=status,
                description=description,
                tags=tag_strs,
                style=style,
                subtasks=[],
            )
        elif active_todo:
            # check for checkbox if we're nested inside a todo
            checkbox = CHECKBOX_RE.match(line)
            if checkbox:
                checkbox_status, desc = checkbox.groups()
                active_todo.subtasks.append((checkbox_status == "x", desc))
            else:
                yield active_todo
                active_todo = None

    # make sure to yield final line if needed
    if active_todo:
        yield active_todo


def get_todo_sort_func(keys):
    def sort_func(item):
        ikey = []
        for key in keys:
            if key == "status":
                ikey.append(item.status_sort())
            elif key == "due":
                ikey.append(item.due())
            elif key == "file":
                ikey.append(item.file)
        return ikey

    return sort_func


def apply_filter(items, rule):
    key, val = rule.split(":")
    if key == "status":
        return [item for item in items if item.status == val]
    else:
        return [item for item in items if rule in item.tags]


@cli.command()
@click.argument("dirname", default="")
@click.option("--sort", "-s")
@click.option("--filter", "-f", multiple=True)
def todos(dirname, sort, filter):
    # scan files
    output = []  # list of data
    for file in get_files(dirname):
        output += pull_todos(file)

    # filter
    for rule in filter:
        output = apply_filter(output, rule)

    # do sorting
    do_sorting(output, sort, ["status", "due"], get_todo_sort_func)

    # display
    table = lod_table(output)
    console.print(table)


# ls command #####


@dataclass
class LsItem:
    file: str
    modified: datetime.datetime
    words: int
    todos: int
    style: str

    def fields(self):
        return [
            "file",
            "modified",
            "words",
            "todos",
        ]

    def to_row(self):
        return [
            self.file,
            human_readable_date(self.modified),
            str(self.words),
            str(self.todos),
        ]


def get_ls_sort_func(keys):
    def sort_func(item):
        ikey = []
        for key in keys:
            if key == "file":
                ikey.append(item.file)
            elif key == "words":
                ikey.append(item.words)
            elif key == "modified":
                ikey.append(item.modified)
            elif key == "todos":
                ikey.append(item.todos)
        return ikey

    return sort_func


def human_readable_date(dt: datetime.datetime) -> str:
    delta = now - dt
    if delta < datetime.timedelta(hours=1):
        return f"{int(delta.total_seconds() / 60)}m ago"
    elif delta < datetime.timedelta(days=1):
        return f"{int(delta.total_seconds() / 3600)}h ago"
    else:
        return f"{delta.days}d ago"


def scan_contents(file: pathlib.Path) -> dict:
    text = file.read_text()
    words = text.split()
    return {"words": len(words), "todos": len(TODO_TODO_RE.findall(text))}


@cli.command()
@click.argument("dirname", default="")
@click.option("--sort", "-s")
def ls(dirname, sort):
    # scan files
    output = []
    for file in get_files(dirname):
        st = file.stat()
        modified = datetime.datetime.fromtimestamp(st.st_mtime)
        scan = scan_contents(file)
        output.append(
            LsItem(
                file=file.name,
                modified=modified,
                style="yellow" if scan["todos"] else "white",
                **scan,
            )
        )

    # sort
    do_sorting(output, sort, ["file", "modified"], get_ls_sort_func)

    # display
    table = lod_table(output)
    console.print(table)


if __name__ == "__main__":
    cli()
