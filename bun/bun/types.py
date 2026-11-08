INT = "int"
FLOAT = "float"
STRING = "string"
BOOL = "bool"
NULL = "null"
ANY = "any"
LIST = "list"
DICT = "dict"
FN = "fn"
SECRET = "secret"
SET = "set"
STRUCT = "struct"
ENUM = "enum"
RESULT = "result"
OPTION = "option"

# The names that are another name.  A `number` is a `float` and a `text` is
# a `string`: the alias is kept in the message of an error, so a program
# that says `number` is told about a `number`.
NUMBER = "number"
TEXT = "text"

TYPE_NAMES = frozenset(
    {INT, FLOAT, STRING, BOOL, NULL, ANY, LIST, DICT, FN, SECRET, SET,
     STRUCT, ENUM, RESULT, OPTION, NUMBER, TEXT})

# The type every alias stands for.
ALIASES = {NUMBER: FLOAT, TEXT: STRING}

# The marker of a builtin that takes any number of arguments, the way
# `print` does.
VARARGS = "*"

BUILTIN_SIGNATURES = {
    "print": [((VARARGS,), NULL)],
    "len": [((ANY,), INT)],
    "range": [((INT,), LIST), ((INT, INT), LIST), ((INT, INT, INT), LIST)],
    "str": [((ANY,), STRING)],
    "input": [((STRING,), STRING), ((), STRING)],
    "int": [((ANY,), INT), ((ANY, INT), INT)],
    "chr": [((INT,), STRING)],
    "ord": [((STRING,), INT)],
    "float": [((ANY,), FLOAT)],
    "read_file": [((STRING,), STRING)],
    "write_file": [((STRING, STRING), NULL)],
    "append_file": [((STRING, STRING), NULL)],
    "file_exists": [((STRING,), BOOL)],
    "getenv": [((STRING,), ANY)],
    "getenv_or": [((STRING, STRING), STRING)],
    "json_parse": [((STRING,), ANY)],
    "json_stringify": [((ANY,), STRING)],
    "http_get": [((STRING, DICT, ANY), DICT)],
    "http_post": [((STRING, DICT, STRING, ANY), DICT)],
    "http_get_bytes": [((STRING, DICT, ANY), DICT)],
    "http_post_bytes": [((STRING, DICT, STRING, ANY), DICT)],
    "http_post_multipart": [((STRING, DICT, LIST, ANY), DICT)],
    "write_bytes": [((STRING, LIST), INT)],
    "read_bytes": [((STRING,), LIST)],
    "bytes_slice": [((ANY, INT, INT), LIST)],
    "bytes_append": [((ANY, ANY), INT)],
    "exec": [((LIST,), DICT), ((LIST, INT), DICT), ((LIST, FLOAT), DICT)],
    "eval": [((STRING,), ANY)],
    "now": [((), FLOAT)],
    "run_language": [((STRING, STRING), DICT),
                     ((STRING, STRING, LIST), DICT),
                     ((STRING, STRING, LIST, FLOAT), DICT),
                     ((STRING, STRING, LIST, INT), DICT)],
    "installed_languages": [((), LIST)],
    "regex_match": [((STRING, STRING), BOOL)],
    "regex_search": [((STRING, STRING), STRING)],
    "regex_findall": [((STRING, STRING), LIST)],
    "regex_replace": [((STRING, STRING, STRING), STRING)],
    "regex_groups": [((STRING, STRING), LIST)],
    "csv_parse": [((STRING,), LIST)],
    "csv_build": [((LIST,), STRING)],
    "html_escape": [((STRING,), STRING)],
    "html_unescape": [((STRING,), STRING)],
    "split_lines": [((STRING,), LIST)],
    "slugify": [((STRING,), STRING)],
    "has_builtin": [((STRING,), BOOL)],
    "quantum_apply": [((LIST, LIST, INT), LIST)],
    "quantum_controlled": [((LIST, LIST, INT, INT), LIST)],
    "quantum_probabilities": [((LIST,), LIST)],
    "quantum_norm": [((LIST,), FLOAT)],
    "quantum_sample": [((LIST, FLOAT), INT)],
    "quantum_measure": [((LIST, INT, FLOAT), DICT)],
    "quantum_expectation": [((LIST, LIST, INT), FLOAT)],
    "quantum_fidelity": [((LIST, LIST), FLOAT)],
    "quantum_flip_sign": [((LIST, INT), LIST)],
    "quantum_swap": [((LIST, INT, INT), LIST)],
    "gcd": [((INT, INT), INT)],
    "lcm": [((INT, INT), INT)],
    "factorial": [((INT,), INT)],
    "clamp": [((ANY, ANY, ANY), ANY)],
    "sign": [((ANY,), INT)],
    "now_ms": [((), INT)],
    "uuid": [((), STRING)],
    "crc32": [((ANY,), INT)],
    "file_size": [((STRING,), INT)],
    "rea_analyze": [((STRING,), DICT)],
    "rea_exports": [((STRING,), STRING)],
    "rea_decompile": [((STRING, STRING), STRING)],
    "sleep": [((FLOAT,), NULL)],
    "spawn": [((FN,), DICT)],
    "task_join": [((DICT,), ANY)],
    "task_done": [((DICT,), BOOL)],
    "cancel": [((DICT,), NULL)],
    "task_cancelled": [((DICT,), BOOL), ((), BOOL)],
    "sandbox_enter": [((DICT,), NULL)],
    "sandbox_exit": [((), NULL)],
    "mutex": [((), DICT)],
    "lock": [((DICT,), NULL)],
    "unlock": [((DICT,), NULL)],
    "ffi_load": [((STRING,), DICT)],
    "list_dir": [((STRING,), LIST)],
    "make_dir": [((STRING,), NULL)],
    "exit": [((INT,), NULL)],
    "args": [((), LIST)],
    "sha256": [((STRING,), LIST), ((ANY,), LIST)],
    "sha1": [((STRING,), LIST), ((ANY,), LIST)],
    "md5": [((ANY,), STRING)],
    "pbkdf2_sha512": [((ANY, ANY, INT), LIST), ((ANY, ANY, INT, INT), LIST)],
    "base64_encode": [((ANY,), STRING)],
    "gzip_decompress": [((ANY,), LIST)],
    "base64_decode": [((STRING,), LIST)],
    "random_bytes": [((INT,), LIST)],
    "random": [((), FLOAT)],
    "random_int": [((INT, INT), INT)],
    "aes_ige_encrypt": [((ANY, ANY, ANY), LIST)],
    "aes_ige_decrypt": [((ANY, ANY, ANY), LIST)],
    "aes_ctr_crypt": [((ANY, ANY, ANY), LIST)],
    "rsa_encrypt": [((ANY, STRING, INT), LIST)],
    "pow_mod": [((ANY, ANY, ANY), ANY)],
    "tcp_connect": [((STRING, INT), DICT)],
    "tcp_listen": [((STRING, INT), DICT), ((STRING,), DICT)],
    "tcp_accept": [((DICT,), DICT), ((DICT, ANY), DICT)],
    "tcp_close": [((DICT,), BOOL)],
    "tcp_write": [((DICT, ANY), BOOL)],
    "tcp_read": [((DICT, INT), LIST)],
    "tcp_set_timeout": [((DICT, ANY), BOOL)],
    "tcp_tls_connect": [((STRING, INT), DICT), ((STRING, INT, LIST), DICT), ((STRING, INT, LIST, STRING), DICT)],
    "h2_connect": [((STRING, INT), DICT), ((STRING, INT, STRING), DICT), ((STRING, INT, STRING, LIST), DICT)],
    "h2_request": [((DICT, STRING), DICT), ((DICT, STRING, STRING), DICT), ((DICT, STRING, STRING, ANY), DICT)],
    "h2_close": [((DICT,), BOOL)],
    "bigint_from_bytes": [((ANY,), LIST)],
    "bigint_to_bytes": [((ANY,), LIST), ((ANY, INT), LIST)],
    "bigint_from_int": [((INT,), LIST)],
    "bigint_to_int": [((ANY,), INT)],
    "bigint_mul": [((ANY, ANY), LIST)],
    "bigint_add": [((ANY, ANY), LIST)],
    "bigint_sub": [((ANY, ANY), LIST)],
    "bigint_mod": [((ANY, ANY), LIST)],
    "bigint_div": [((ANY, ANY), LIST)],
    "bigint_gcd": [((ANY, ANY), LIST)],
    "bigint_mul_mod": [((INT, INT, INT), INT)],
    "bigint_mul_mod_bytes": [((ANY, ANY, ANY), LIST)],
    "bigint_cmp": [((ANY, ANY), INT)],
    "bigint_pow_mod": [((ANY, ANY, ANY), LIST)],
    "bigint_factorize": [((ANY,), LIST)],
    "double_from_bits": [((INT,), FLOAT)],
    "double_to_bits": [((FLOAT,), INT)],
    "utf8_bytes": [((STRING,), LIST)],
    "utf8_string": [((ANY,), STRING)],
    "type_of": [((ANY,), STRING)],
    "bool": [((ANY,), BOOL)],
    "abs": [((ANY,), FLOAT)],
    "sum": [((LIST,), FLOAT)],
    "any": [((LIST,), BOOL)],
    "all": [((LIST,), BOOL)],
    "min": [((LIST,), ANY)],
    "max": [((LIST,), ANY)],
    "zip": [((LIST, LIST), LIST)],
    "enumerate": [((LIST,), LIST)],
    "sorted": [((LIST,), LIST)],
    "reversed": [((LIST,), LIST)],
    "next": [((ANY,), ANY), ((ANY, ANY), ANY)],
    "send": [((ANY, ANY), ANY)],
    "set": [((), SET), ((LIST,), SET)],
    # The builtins of the self hosted front end. They exist so the front end
    # can run on its own runtime, a normal program does not have them.
    "run_code": [((ANY,), NULL)],
    "type_error": [((STRING, INT, INT), NULL)],
    "module_path": [((STRING, STRING), STRING)],
    "read_module": [((STRING, STRING), STRING)],
    "dump": [((ANY,), STRING)],
    "secret": [((ANY,), SECRET)],
    "url_encode": [((STRING,), STRING)],
    "url_decode": [((STRING,), STRING)],
    "starts_with": [((STRING, STRING), BOOL)],
    "ends_with": [((STRING, STRING), BOOL)],
    "substring": [((STRING, INT, INT), STRING), ((STRING, INT), STRING)],
    "index_of": [((STRING, STRING), INT)],
    "split": [((STRING, STRING), LIST), ((STRING, STRING, INT), LIST)],
    "join": [((LIST, STRING), STRING)],
    "replace": [((STRING, STRING, STRING), STRING)],
    "trim": [((STRING,), STRING)],
    "lower": [((STRING,), STRING)],
    "upper": [((STRING,), STRING)],
    "Ok": [((ANY,), RESULT)],
    "Err": [((ANY,), RESULT)],
    "is_ok": [((ANY,), BOOL)],
    "is_err": [((ANY,), BOOL)],
    "some": [((ANY,), OPTION)],
    "none": [((), OPTION)],
    "is_some": [((ANY,), BOOL)],
    "is_none": [((ANY,), BOOL)],    # BEGIN GENERATED MATURITY WAVE 1
    "hmac_sha256_hex": [((STRING, STRING), STRING)],
    "hmac_sha512_hex": [((STRING, STRING), STRING)],
    "base64url_encode": [((ANY,), STRING)],
    "base64url_decode": [((STRING,), LIST)],
    "hex_encode": [((ANY,), STRING)],
    "hex_decode": [((STRING,), LIST)],
    "gzip_compress": [((ANY,), LIST)],
    "sha512_hex": [((ANY,), STRING)],
    "blake2b_hex": [((ANY,), STRING)],
    "timing_safe_equal": [((STRING, STRING), BOOL)],
    "time_format": [((FLOAT, STRING), STRING)],
    "time_parse_iso": [((STRING,), FLOAT)],
    "time_iso": [((FLOAT,), STRING)],
    "time_parts": [((FLOAT,), DICT)],
    "time_add": [((FLOAT, FLOAT), FLOAT)],
    "time_diff": [((FLOAT, FLOAT), FLOAT)],
    "time_weekday": [((FLOAT,), INT)],
    "time_is_leap": [((INT,), BOOL)],
    "time_days_in_month": [((INT, INT), INT)],
    "time_epoch_ms": [((FLOAT,), INT)],
    "format": [((STRING, DICT), STRING)],
    "pad_left": [((STRING, INT, STRING), STRING)],
    "pad_right": [((STRING, INT, STRING), STRING)],
    "center": [((STRING, INT, STRING), STRING)],
    "title_case": [((STRING,), STRING)],
    "swap_case": [((STRING,), STRING)],
    "truncate": [((STRING, INT), STRING)],
    "word_wrap": [((STRING, INT), STRING)],
    "unicode_normalize": [((STRING,), STRING)],
    "levenshtein": [((STRING, STRING), INT)],
    "url_parse": [((STRING,), DICT)],
    "url_build": [((DICT,), STRING)],
    "query_parse": [((STRING,), DICT)],
    "query_build": [((DICT,), STRING)],
    "status_text": [((INT,), STRING)],
    "cookie_parse": [((STRING,), DICT)],
    "mime_from_path": [((STRING,), STRING)],
    "status_class": [((INT,), INT)],
    "percent_encode": [((STRING,), STRING)],
    "header_parse": [((STRING,), DICT)],
    "struct_pack": [((STRING, INT), LIST)],
    "struct_unpack": [((STRING, LIST), INT)],
    "toml_parse": [((STRING,), DICT)],
    "json_pointer": [((ANY, STRING), ANY)],
    "json_equal": [((ANY, ANY), BOOL)],
    "decimal_add": [((STRING, STRING), STRING)],
    "bitset_new": [((INT,), DICT)],
    "bitset_set": [((DICT, INT), DICT)],
    "bitset_get": [((DICT, INT), BOOL)],
    "ordered_dict_new": [((), DICT)],
    "ordered_dict_keys": [((DICT,), LIST)],
    "uuid_v4": [((), STRING)],
    "ulid": [((), STRING)],
    "semver_compare": [((STRING, STRING), INT)],
    "semver_satisfies": [((STRING, STRING), BOOL)],
    # END GENERATED MATURITY WAVE 1

}


def is_known_type(name):
    return name in TYPE_NAMES


# The bounds a type parameter of a function may carry.  A bound is a
# class of types: `Num` is the types a number may have, `Ord` the types
# that may be put in order, and so on.  A bound with an empty set is
# satisfied by every type.
BOUND_NAMES = frozenset({"Num", "Ord", "Eq", "Hash", "Show"})

BOUND_TYPES = {
    "Num": frozenset({INT, FLOAT}),
    "Ord": frozenset({INT, FLOAT, STRING}),
    "Eq": frozenset(),
    "Hash": frozenset({INT, FLOAT, STRING, BOOL}),
    "Show": frozenset(),
}


def base_type(name):
    """The name of a type, without its type arguments.

    The type `list<int>` has the base `list`, and the type `int` has
    the base `int`.
    """
    if not name:
        return name
    index = name.find("<")
    if index < 0:
        return name
    return name[:index]


def type_args(name):
    """The type arguments of a type.

    The type `list<int>` has the argument `int`, and the type `int` has
    no argument.
    """
    if not name:
        return []
    index = name.find("<")
    if index < 0:
        return []
    return [part.strip() for part in name[index + 1:-1].split(",")]


def satisfies_bound(name, bound):
    """Report whether a type satisfies a bound.

    The type `any` satisfies every bound: it is the way out of the
    check of a type, and a bound is a check of a type.
    """
    if bound is None:
        return True
    if name == ANY:
        return True
    allowed = BOUND_TYPES.get(bound)
    if allowed is None or not allowed:
        return True
    return name in allowed


def is_assignable(source, target):
    target = ALIASES.get(target, target)
    source = ALIASES.get(source, source)
    if source == target:
        return True
    if source == ANY or target == ANY:
        return True
    if source == INT and target == FLOAT:
        return True
    if source == NULL:
        return True
    # A type with type arguments is a type with the same name: the
    # arguments of a container are a promise of the program, not a
    # check of the language.
    source_base = base_type(source)
    target_base = base_type(target)
    if source_base != source or target_base != target:
        return source_base == target_base
    return False
