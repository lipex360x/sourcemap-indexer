from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass
from enum import StrEnum

from sourcemap_indexer.lib.either import Either, left, right


class Language(StrEnum):
    PY = "py"
    SH = "sh"
    TS = "ts"
    TSX = "tsx"
    JS = "js"
    SQL = "sql"
    MD = "md"
    YAML = "yaml"
    JSON = "json"
    TOML = "toml"
    PHP = "php"
    RUBY = "ruby"
    GO = "go"
    RUST = "rust"
    JAVA = "java"
    KOTLIN = "kotlin"
    SWIFT = "swift"
    SCALA = "scala"
    C = "c"
    CPP = "cpp"
    CSHARP = "csharp"
    OBJC = "objc"
    LUA = "lua"
    DART = "dart"
    ELIXIR = "elixir"
    ERLANG = "erlang"
    HASKELL = "haskell"
    OCAML = "ocaml"
    CLOJURE = "clojure"
    PERL = "perl"
    R = "r"
    JULIA = "julia"
    VUE = "vue"
    SVELTE = "svelte"
    ASTRO = "astro"
    CSS = "css"
    SCSS = "scss"
    LESS = "less"
    HTML = "html"
    XML = "xml"
    GRAPHQL = "graphql"
    PROTO = "proto"
    DOCKERFILE = "dockerfile"
    MAKEFILE = "makefile"
    TERRAFORM = "terraform"
    NIX = "nix"
    OTHER = "other"


Layer = str

_DEFAULT_LAYERS: frozenset[str] = frozenset(
    {"domain", "infra", "application", "cli", "hook", "lib", "config", "doc", "test", "unknown"}
)


class Stability(StrEnum):
    CORE = "core"
    STABLE = "stable"
    EXPERIMENTAL = "experimental"
    DEPRECATED = "deprecated"
    UNKNOWN = "unknown"


class SideEffect(StrEnum):
    WRITES_FS = "writes_fs"
    SPAWNS_PROCESS = "spawns_process"
    NETWORK = "network"
    GIT = "git"
    ENVIRON = "environ"


_HEX_RE = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True, slots=True)
class ContentHash:
    hex_value: str

    def __post_init__(self) -> None:
        if not _HEX_RE.fullmatch(self.hex_value):
            raise ValueError("invalid-hash-format")

    @classmethod
    def create(cls, hex_value: str) -> Either[str, ContentHash]:
        try:
            return right(cls(hex_value))
        except ValueError as error:
            return left(str(error))

    @classmethod
    def from_bytes(cls, data: bytes) -> Either[str, ContentHash]:
        return right(cls(hashlib.sha256(data).hexdigest()))


@dataclass(frozen=True, slots=True)
class ItemId:
    uuid_str: str

    def __post_init__(self) -> None:
        try:
            uuid.UUID(self.uuid_str)
        except ValueError:
            raise ValueError("invalid-uuid-format") from None

    @classmethod
    def generate(cls) -> ItemId:
        return cls(str(uuid.uuid4()))

    @classmethod
    def from_string(cls, uuid_string: str) -> Either[str, ItemId]:
        try:
            return right(cls(uuid_string))
        except ValueError as error:
            return left(str(error))
