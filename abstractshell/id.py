from enum import Enum
import re

_id_re = r"(\d+)\(([^\)]*)\)"
_id_re_compiled = re.compile(_id_re)
_id_parse = re.compile(rf"uid\={_id_re}\s+gid\={_id_re}\s+groups=(.*)")


def id_parse(out):
    print(_id_parse)

    match = _id_parse.match(out)
    if not match:
        return None

    uid, user, gid, group, groups = match.groups()
    ctx = {"uid": (int(uid), user), "gid": (int(gid), group), "groups": []}

    groups = groups.split(",")
    for group in groups:
        match = _id_re_compiled.match(group)
        if not match:
            continue

        gid, group = match.groups()
        ctx["groups"].append((int(gid), group))
    return ctx
