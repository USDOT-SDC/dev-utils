from tabulate import tabulate
from log import Log
import os
import json

logger = Log()


def cls() -> None:
    """Clears the screen of any command interface"""
    os.system("cls" if os.name == "nt" else "clear")


def dd(data: any, debug: bool = False) -> None:
    """Dumps any variable data as a readable json

    Args:
        data (any): any data or object
        debug (bool, optional): Turns the function on or off. Defaults to False.
    """
    if debug:
        print(json.dumps(data, ensure_ascii=False, indent=2, default=str))


def get_table_title(title, subtitle=""):
    res = "\n"
    title_len = len(title)
    subtitle_len = len(subtitle)
    max_len = max(title_len, subtitle_len)
    dif_len = abs(title_len - subtitle_len)
    if title_len == subtitle_len:
        title_pad = ""
        subtitle_pad = ""
    elif title_len > subtitle_len:
        title_pad = ""
        subtitle_pad = " " * dif_len
    else:
        title_pad = " " * dif_len
        subtitle_pad = ""

    outline_chars = "─" * max_len
    res = res + f"╭──{outline_chars}──╮" + "\n"
    res = res + f"│  {title}  {title_pad}│" + "\n"
    if subtitle:
        res = res + f"│  {subtitle}  {subtitle_pad}│" + "\n"

    return res


def print_table(list_of_dict, columns_to_print=[], sort_by=False, title="", subtitle=""):
    header = get_table_title(title, subtitle)
    if not columns_to_print and not sort_by:
        print(header + tabulate(list_of_dict, headers="keys", tablefmt="rounded_outline", intfmt=",", floatfmt=".3f"))
    elif not columns_to_print and sort_by:
        if list_of_dict:
            if list_of_dict[0].get(sort_by, False):
                list_of_dict_sorted = sorted(list_of_dict, key=lambda d: d[sort_by])
                list_of_dict = list_of_dict_sorted
            else:
                logger.warning("sort by not found in table")
    elif columns_to_print and not sort_by:
        list_of_dict_to_print = []
        for n_dict in list_of_dict:
            list_of_dict_to_print.append({key: value for key, value in n_dict.items() if key in columns_to_print})
        if list_of_dict_to_print:
            print(header + tabulate(list_of_dict_to_print, headers="keys", tablefmt="rounded_outline", intfmt=",", floatfmt=".3f"))
    elif columns_to_print and sort_by:
        if list_of_dict:
            if list_of_dict[0].get(sort_by, False):
                list_of_dict_sorted = sorted(list_of_dict, key=lambda d: d[sort_by])
                list_of_dict = list_of_dict_sorted
            else:
                logger.warning("sort by not found in table")
            list_of_dict_to_print = []
            for n_dict in list_of_dict:
                list_of_dict_to_print.append({key: value for key, value in n_dict.items() if key in columns_to_print})
            if list_of_dict_to_print:
                print(
                    header + tabulate(list_of_dict_to_print, headers="keys", tablefmt="rounded_outline", intfmt=",", floatfmt=".3f")
                )
    else:
        print(header + tabulate(list_of_dict, headers="keys", tablefmt="rounded_outline", intfmt=",", floatfmt=".3f"))
