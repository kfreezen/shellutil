from enum import Enum


class IdLex(Enum):
    SEP = "sep"
    COMMA = ","
    EQUALS = "="
    TOK = "tok"
    PAREN = "paren"


class IdTok(Enum):
    KEYWORD = "keyword"
    ID = "id"
    TOK = "tok"
    USERNAME = "username"


_id_special = {
    IdLex.SEP: " \t\r\n",
    IdLex.COMMA: ",",
    IdLex.EQUALS: "=",
    IdLex.PAREN: "()",
}


def _identify_tok_type(c):
    for (tok_type, s) in _id_special.items():
        if c in s:
            return tok_type

    return IdLex.TOK


def _id_lex(s):
    buf = ""

    tok_type = None
    for c in s:
        c_tok_type = _identify_tok_type(c)
        if tok_type is None:
            tok_type = c_tok_type

        if tok_type != c_tok_type:
            next_tok_type = tok_type
            tok_type = c_tok_type
            next_tok = buf
            buf = ""
            yield (next_tok_type, next_tok)

        buf += c


def _id_tok(s):
    next_expected = None

    for (lex_type, lex) in _id_lex(s):
        if next_expected and lex_type not in next_expected:
            raise ValueError(f"Invalid id string: {next_expected}, {lex_type}")

        next_expected = None

        if lex_type == IdLex.TOK:
            if lex in ("uid", "gid", "groups"):
                yield (IdTok.KEYWORD, lex)
            else:
                try:
                    int(lex)
                    yield (IdTok.ID, int(lex))
                except:
                    yield (IdTok.TOK, lex)
        if lex_type == IdLex.EQUALS:
            next_expected = [IdLex.TOK]
            continue
        if lex_type == IdLex.PAREN:
            next_expected = [IdLex.TOK, IdLex.SEP, IdLex.COMMA]
            continue


def id_parse(tokens):
    id_tok = next(tokens)
    user_tok = next(tokens)

    if id_tok[0] != IdTok.ID and user_tok[0] != IdTok.TOK:
        raise ValueError("Unexpected token stream")
    return (id_tok[1], user_tok[1])


def uid_parse(tokens, ctx):
    ctx["uid"] = id_parse(tokens)


def gid_parse(tokens, ctx):
    ctx["gid"] = id_parse(tokens)


def groups_parse(tokens, ctx):
    groups = ctx.setdefault("groups", [])
    groups.append(id_parse(tokens))

    try:
        groups_parse(tokens, ctx)
    except StopIteration:
        pass


_parsers = {"uid": uid_parse, "gid": gid_parse, "groups": groups_parse}


def parse_id_string(s):
    tokens = _id_tok(s)
    ctx = {}

    for (tok_type, tok) in tokens:
        if tok_type == IdTok.KEYWORD:
            _parsers[tok](tokens, ctx)

    return ctx
