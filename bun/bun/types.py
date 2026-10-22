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

# The names that are another name.  A `number` is a `float` and a `text` is
# a `string`: the alias is kept in the message of an error, so a program
# that says `number` is told about a `number`.
NUMBER = "number"
TEXT = "text"

TYPE_NAMES = frozenset(
    {INT, FLOAT, STRING, BOOL, NULL, ANY, LIST, DICT, FN, SECRET, SET,
     NUMBER, TEXT})

# The type every alias stands for.
ALIASES = {NUMBER: FLOAT, TEXT: STRING}

BUILTIN_SIGNATURES = {
    "print": [((ANY,), NULL)],
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
    "http_post_multipart": [((STRING, DICT, LIST, ANY), DICT)],
    "write_bytes": [((STRING, LIST), INT)],
    "read_bytes": [((STRING,), LIST)],
    "bytes_slice": [((ANY, INT, INT), LIST)],
    "bytes_append": [((ANY, ANY), INT)],
    "exec": [((LIST,), DICT), ((LIST, INT), DICT), ((LIST, FLOAT), DICT)],
    "eval": [((STRING,), ANY)],
    "now": [((), FLOAT)],
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
}


def is_known_type(name):
    return name in TYPE_NAMES


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
    return False
