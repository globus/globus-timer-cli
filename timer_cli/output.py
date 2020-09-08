import json
from typing import List

import click
import requests


def make_table(headers: List[str], rows: List[List[str]]) -> str:
    max_cell_width = max(map(len, headers))
    if rows:
        max_cell_width = max(
            max_cell_width,
            max(len(cell) for row in rows for cell in row),
        )
    formatted_header = " | ".join(cell.ljust(max_cell_width) for cell in headers)
    formatted_rows = [
        " | ".join(cell.ljust(max_cell_width) for cell in row)
        for row in rows
    ]
    max_row_width = len(formatted_header)
    if formatted_rows:
        max_row_width = max(max_row_width, max(map(len, formatted_rows)))
    separator = "-" * max_row_width
    formatted_rows_block = "\n".join(formatted_rows)
    return f"{formatted_header}\n{separator}\n{formatted_rows_block}"


def show_response(response: requests.Response):
    if response.status_code >= 400:
        click.echo(f"got response code {response.status_code}", err=True)
    click.echo(json.dumps(response.json()))
