from __future__ import annotations
from dataclasses import dataclass
from typing import Any
from functools import reduce
from itertools import takewhile
from pathlib import Path
import json
import sys


# datastructs
@dataclass(frozen=True)
class HBox:
	pass
@dataclass(frozen=True)
class VBox:
	indent: int
@dataclass(frozen=True)
class HVBox:
	indent: int
@dataclass(frozen=True)
class HOVBox:
	indent: int
Block = HBox | VBox | HVBox | HOVBox

PpTag = str
@dataclass(frozen=True)
class Empty:
	pass
@dataclass(frozen=True)
class Str:
	s: str
	tag: PpTag | None = None
@dataclass(frozen=True)
class Glue:
	parts: tuple[Pp, ...]
@dataclass(frozen=True)
class Box:
	kind: Block
	body: Pp
@dataclass(frozen=True)
class Tag:
	tag: PpTag
	body: Pp
@dataclass(frozen=True)
class Break:
	spaces: int
	offset: int
@dataclass(frozen=True)
class ForceNewline:
	pass
@dataclass(frozen=True)
class Comment:
	lines: tuple[str, ...]
Pp = Empty | Str | Glue | Box | Tag | Break | ForceNewline | Comment

def block_of_json(json: list[Any]) -> Block:
	match json:
		case ["Pp_hbox"]: return HBox()
		case ["Pp_vbox", n]: return VBox(n)
		case ["Pp_hvbox", n]: return HVBox(n)
		case ["Pp_hovbox", n]: return HOVBox(n)
	raise ValueError(f"not a json block: {json}")

def pp_of_json(json: list[Any]) -> Pp:
	match json:
		case ["Ppcmd_empty"]: return Empty()
		case ["Ppcmd_string", s]: return Str(s)
		case ["Ppcmd_glue", ps]: return Glue(tuple(pp_of_json(p) for p in ps))
		case ["Ppcmd_box", k, body]: return Box(block_of_json(k), pp_of_json(body))
		case ["Ppcmd_tag", t, body]: return Tag(t, pp_of_json(body))
		case ["Ppcmd_print_break", sp, o]: return Break(sp, o)
		case ["Ppcmd_force_newline"]: return ForceNewline()
		case ["Ppcmd_comment", ls]: return Comment(tuple(ls))
	raise ValueError(f"not a json pp: {json}")


# styling helpers
STYLES = {
	"constr.keyword": "1;34",
	"constr.variable": "36",
	"constr.reference": "32",
	"constr.type": "33",
	"constr.notation": "35",
	"message.error": "1;31",
}

def styled(s: str, tag: PpTag | None) -> str:
	code = STYLES.get(tag) if tag else None
	return f"\x1b[{code}m{s}\x1b[0m" if code else s

def tagged(tag: PpTag, pp: Pp) -> Pp:	# push tag down, keep innermost
	match pp:
		case Str(s, None): return Str(s, tag)
		case Box(kind, body): return Box(kind, Tag(tag, body))
		case _: return pp


# actual layouting
def newline(indent: int) -> tuple[str, int]:
	col = max(indent, 0)
	s = "\n" + " " * col
	return s, col

def clean(pp: Pp) -> list[Pp]:	# remove useless ppboxes, keep tags
	match pp:
		case Empty(): return []
		case Glue(parts): return [unglued for part in parts
                              for unglued in clean(part)]
		case Tag(t, body): return [tagged(t, item) for item in clean(body)]
		case Comment(ls): return [a for i, l in enumerate(ls)
                              for a in ([Break(1, 0)] if i else []) + [Str(l)]]
		case _: return [pp]

def get_indent(kind: Block) -> int:
  match kind:
    case HBox(): return 0
    case VBox(n) | HVBox(n) | HOVBox(n): return n

def width_of(pp: Pp) -> int:	# if was one-lined
	match pp:
		case Str(s): return len(s)
		case Break(n, _): return n
		case Box(_, body):
			width_sum = lambda acc, w: acc + width_of(w)
			return reduce(width_sum, clean(body), 0)
		case _: return 0

def prints_as_one_line(kind: Block, fits: bool, spaces: int, rest: list[Pp], width: int) -> bool:	# whether it prints as one line or a new line
	match kind:
		case HBox(): return True
		case VBox(): return False
		case HVBox(): return fits
		case HOVBox():
			chunk = takewhile(lambda pp: not isinstance(pp, Break), rest)
			return fits or spaces + sum(map(width_of, chunk)) <= width

def render(box: Box, col: int, width: int) -> tuple[str, int]:
	items = clean(box.body)
	indent = col + get_indent(box.kind)
	fits = sum(map(width_of, items)) <= width - col

	def step(state: tuple[str, int], next_items: tuple[int, Pp]) -> tuple[str, int]:
		txt, col = state
		i, pp = next_items
		new_txt = ""
		new_col = col
		match pp:
			case Str(s, tag):
				new_txt = styled(s, tag)
				new_col = col + len(s)
			case Box():
				new_txt, new_col = render(pp, col, width)
			case ForceNewline():
				new_txt, new_col = newline(indent)
			case Break(sp, o):
				if (prints_as_one_line(box.kind, fits, sp, items[i + 1:], width - col)):
					new_txt = " " * sp
					new_col = col + sp
				else:
					new_txt, new_col = newline(indent + o)
		return txt + new_txt, new_col

	return reduce(step, enumerate(items), ("", col))


# TODO remove when pushing
def main():
	text = Path(sys.argv[1]).read_text()
	data, _ = json.JSONDecoder().raw_decode(text.lstrip())

	pp = pp_of_json(data)
	width = int(sys.argv[2]) if len(sys.argv) > 2 else 78

	res = render(Box(HOVBox(0), pp), 0, width)[0]
	print(res)

if __name__ == "__main__":
	main()
