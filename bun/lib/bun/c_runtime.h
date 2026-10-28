/* The runtime of the C backend of Bun.
 *
 * The runtime holds the values of the language, the scopes, the errors
 * and the operations of the core library.  The emitter writes a program
 * that uses this runtime, and the system compiler turns that program
 * into a binary.
 *
 * The values are a tagged union: null, a boolean, an integer, a float, a
 * string, a list, a dictionary, a function and a builtin.  The heap
 * objects live in an arena that is released when the program ends, so
 * there is one owner and no cycles to chase.
 *
 * The errors use `setjmp` and `longjmp`: the handler stack is global,
 * so a `try` in a function catches the error of the function it calls,
 * exactly like the register machine does.
 */

#ifndef BUN_C_RUNTIME_H
#define BUN_C_RUNTIME_H

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <stdarg.h>
#include <math.h>
#include <setjmp.h>
#include <ctype.h>
#include <errno.h>
#include <pthread.h>
#include <time.h>

/* ------------------------------------------------------------------ */
/* The values                                                          */
/* ------------------------------------------------------------------ */

typedef enum {
    BUN_NULL = 0,
    BUN_BOOL,
    BUN_INT,
    BUN_FLOAT,
    BUN_STR,
    BUN_LIST,
    BUN_DICT,
    BUN_SET,
    BUN_FUNC,
    BUN_BUILTIN,
    BUN_SECRET,
    BUN_STRUCT
} BunTag;

typedef struct BunEnv BunEnv;
typedef struct BunObj BunObj;
typedef struct BunValue BunValue;

/* A function of the program takes the environment of the call, the
   arguments of the call and the keyword arguments of the call.  The
   arguments are bound in the frame of the function, so a function that
   makes no environment costs nothing but its frame. */
typedef BunValue (*BunFn)(BunEnv *env, BunValue *args, int argc,
                          BunValue kwargs);
typedef BunValue (*BunBuiltinFn)(BunValue *args, int count);

struct BunValue {
    BunTag tag;
    union {
        int64_t i;
        double f;
        int b;
        BunObj *obj;
    } as;
};

typedef struct BunParam {
    const char *name;
    int kind;              /* 0 = positional, 1 = vararg, 2 = kwarg, 3 = kwonly */
    int has_default;
    BunFn default_code;
    int slot;              /* the slot of the frame, or -1 for the environment */
    int borrowed;          /* the value is not copied when it is bound */
} BunParam;

struct BunObj {
    BunTag tag;
    int builtin_id;
    BunFn fn;
    BunBuiltinFn builtin;
    const char *name;
    BunEnv *closure;
    const BunParam *params;
    int param_count;
    int needs_env;         /* the function makes an environment for its call */
    size_t len;
    char *data;          /* the text of a string */
    size_t count;        /* the items of a list, the pairs of a dictionary */
    size_t cap;
    BunValue *items;     /* the items of a list */
    BunValue *keys;      /* the keys of a dictionary */
    BunValue *values;    /* the values of a dictionary */
    int *index;          /* the open addressing table of the keys */
    int index_size;
    BunValue secret;     /* the value that a secret holds */
    const char **field_names;  /* the names of the fields of a struct */
    BunValue *field_values;    /* the values of the fields of a struct */
};

#define BUN_VALUE(tag) ((BunValue){ (tag), { 0 } })

static BunValue bun_null_value(void) { return BUN_VALUE(BUN_NULL); }

static BunValue bun_bool_value(int truth) {
    BunValue value = BUN_VALUE(BUN_BOOL);
    value.as.b = truth ? 1 : 0;
    return value;
}

static BunValue bun_int_value(int64_t number) {
    BunValue value = BUN_VALUE(BUN_INT);
    value.as.i = number;
    return value;
}

static BunValue bun_float_value(double number) {
    BunValue value = BUN_VALUE(BUN_FLOAT);
    value.as.f = number;
    return value;
}

static BunValue bun_obj_value(BunObj *object) {
    BunValue value = BUN_VALUE(object->tag);
    value.as.obj = object;
    return value;
}

/* The pending error of a frame that runs a `finally`. */
typedef struct BunPending {
    BunValue value;
    int has;
} BunPending;

/* The iterator of a loop. */
typedef struct BunIter {
    BunValue *items;
    size_t count;
    size_t at;
    int is_string;
    BunObj *text;
    int is_object;        /* the iterator answers 'next' */
    BunValue object;      /* the value of the iterator protocol */
} BunIter;

/* ------------------------------------------------------------------ */
/* The arena                                                           */
/* ------------------------------------------------------------------ */

typedef struct BunArenaBlock {
    struct BunArenaBlock *next;
    void *data;
} BunArenaBlock;

/* The arena of the thread.  A task of the program runs on a thread of
   its own, and it allocates in an arena of its own, so a lock is not
   taken on every allocation.  When the thread of a task ends, its arena
   moves to the list of the ended tasks: the value a task made is still
   there for the task that joins it. */
static _Thread_local BunArenaBlock *bun_thread_arena = NULL;
static pthread_mutex_t bun_arena_lock = PTHREAD_MUTEX_INITIALIZER;
static BunArenaBlock *bun_ended_arena = NULL;
static pthread_key_t bun_arena_key;
static int bun_arena_key_made = 0;

static void bun_arena_migrate(void) {
    BunArenaBlock *block;
    if (bun_thread_arena == NULL) {
        return;
    }
    pthread_mutex_lock(&bun_arena_lock);
    block = bun_thread_arena;
    while (block->next != NULL) {
        block = block->next;
    }
    block->next = bun_ended_arena;
    bun_ended_arena = bun_thread_arena;
    bun_thread_arena = NULL;
    pthread_mutex_unlock(&bun_arena_lock);
}

static void bun_arena_thread_end(void *value) {
    (void)value;
    bun_arena_migrate();
}

static void bun_arena_init_thread(void) {
    if (!bun_arena_key_made) {
        if (pthread_key_create(&bun_arena_key, bun_arena_thread_end) == 0) {
            bun_arena_key_made = 1;
        }
    }
    if (bun_arena_key_made) {
        pthread_setspecific(bun_arena_key, (void *)&bun_arena_key_made);
    }
}

static void *bun_alloc(size_t size) {
    BunArenaBlock *block = (BunArenaBlock *)malloc(sizeof(BunArenaBlock));
    void *data = calloc(1, size ? size : 1);
    if (!block || !data) {
        fprintf(stderr, "error: out of memory\n");
        exit(1);
    }
    block->data = data;
    block->next = bun_thread_arena;
    bun_thread_arena = block;
    return data;
}

static void bun_arena_release(void) {
    BunArenaBlock *block;
    bun_arena_migrate();
    pthread_mutex_lock(&bun_arena_lock);
    block = bun_ended_arena;
    while (block) {
        BunArenaBlock *next = block->next;
        free(block->data);
        free(block);
        block = next;
    }
    bun_ended_arena = NULL;
    pthread_mutex_unlock(&bun_arena_lock);
}

static BunObj *bun_new_obj(BunTag tag) {
    BunObj *object = (BunObj *)bun_alloc(sizeof(BunObj));
    object->tag = tag;
    return object;
}

/* ------------------------------------------------------------------ */
/* The picture of a failure                                            */
/* ------------------------------------------------------------------ */

/* The emitter writes the lines of the program and the table of the
 * hints, so a failure of the native backend has the same picture as a
 * failure of the machine. */
typedef struct BunHint {
    const char *pattern;
    const char *hint;
} BunHint;

extern const char *const bun_source_file;
extern const char *const *bun_source_lines[];
extern const int bun_source_line_count;
extern const BunHint bun_hints[];

/* The position of the source.  The line and the column have their own
   place, and not one word that holds the two of them: the compiler of the
   system keeps the values of a loop in the registers of the machine when
   the two places are written apart, and the loop of a program is the place
   where the speed matters most. */
static _Thread_local int bun_error_line = 0;
static _Thread_local int bun_error_col = 0;

/* Write the position of the source before an instruction that can fail. */
static void bun_at(int line, int col) {
    bun_error_line = line;
    bun_error_col = col;
}

/* The advice of the error, or NULL when the error has none.  The table is
 * matched in order and the first pattern that is in the message wins. */
static const char *bun_hint_for(const char *message) {
    int i;
    for (i = 0; bun_hints[i].pattern != NULL; i++) {
        if (strstr(message, bun_hints[i].pattern) != NULL) {
            return bun_hints[i].hint;
        }
    }
    return NULL;
}

/* Print the error of a program that ends: the message, the place of the
 * source and the advice. */
static void bun_report_error(const char *message) {
    char number[32];
    const char *hint;
    const char *file;
    int i;
    int pad;
    int line;
    int col;

    fprintf(stderr, "error: %s\n", message);
    line = bun_error_line;
    col = bun_error_col;
    if (line > 0 && line <= bun_source_line_count) {
        file = getenv("BUN_SOURCE_FILE");
        if (file == NULL || file[0] == '\0') {
            file = bun_source_file;
        }
        snprintf(number, sizeof(number), "%d", line);
        pad = (int)strlen(number);
        fprintf(stderr, "  --> %s:%d:%d\n", file, line, col);
        fprintf(stderr, " %*s |\n", pad, "");
        fprintf(stderr, " %s | %s\n", number, bun_source_lines[line - 1]);
        fprintf(stderr, " %*s | ", pad, "");
        for (i = 1; i < col; i++) {
            fputc(' ', stderr);
        }
        fputs("^\n", stderr);
    }
    hint = bun_hint_for(message);
    if (hint != NULL) {
        fprintf(stderr, "  hint: %s\n", hint);
    }
}

/* ------------------------------------------------------------------ */
/* The errors                                                          */
/* ------------------------------------------------------------------ */

typedef struct BunHandler {
    jmp_buf buf;
    int kind;              /* 0 = catch, 1 = finally */
    BunEnv *env;
    struct BunHandler *prev;
} BunHandler;

static _Thread_local BunHandler *bun_handler = NULL;
static _Thread_local char bun_error_message[8192];

static void bun_throw(const char *format, ...) {
    va_list args;
    va_start(args, format);
    vsnprintf(bun_error_message, sizeof(bun_error_message), format, args);
    va_end(args);
    if (!bun_handler) {
        bun_report_error(bun_error_message);
        bun_arena_release();
        exit(1);
    }
    longjmp(bun_handler->buf, 1);
}

static BunHandler *bun_handler_push(int kind, BunEnv *env) {
    BunHandler *handler = (BunHandler *)bun_alloc(sizeof(BunHandler));
    handler->kind = kind;
    handler->env = env;
    handler->prev = bun_handler;
    bun_handler = handler;
    return handler;
}

static void bun_handler_pop(void) {
    if (bun_handler) {
        bun_handler = bun_handler->prev;
    }
}

/* ------------------------------------------------------------------ */
/* The scopes                                                          */
/* ------------------------------------------------------------------ */

typedef struct BunBinding {
    const char *name;
    BunValue value;
    int mutable;
    int deleted;
} BunBinding;

struct BunEnv {
    BunEnv *parent;
    BunBinding *entries;
    int count;
    int cap;
    int *table;            /* the open addressing table of the names */
    int table_size;
};

static BunEnv *bun_env_new(BunEnv *parent) {
    BunEnv *env = (BunEnv *)bun_alloc(sizeof(BunEnv));
    env->parent = parent;
    env->cap = 8;
    env->entries = (BunBinding *)bun_alloc(sizeof(BunBinding) * env->cap);
    env->table_size = 16;
    env->table = (int *)bun_alloc(sizeof(int) * env->table_size);
    for (int index = 0; index < env->table_size; index++) {
        env->table[index] = -1;
    }
    return env;
}

static size_t bun_hash_name(const char *name) {
    size_t hash = 1469598103934665603u;
    while (*name) {
        hash ^= (unsigned char)*name++;
        hash *= 1099511628211u;
    }
    return hash;
}

/* The copy of a value.  A struct is a value type, so a copy of a struct
 * is a new struct with the same fields.  Every other value is shared. */
static BunValue bun_copy_value(BunValue value);
static const char *bun_type_name(BunValue value);

/* The size of the table of an environment is always a power of two, so
 * the slot of a name is a mask and not a division.  A division costs
 * more than the rest of the lookup. */

static void bun_env_rehash(BunEnv *env, int size) {
    int *table = (int *)bun_alloc(sizeof(int) * size);
    for (int index = 0; index < size; index++) {
        table[index] = -1;
    }
    size_t mask = (size_t)size - 1;
    for (int position = 0; position < env->count; position++) {
        size_t slot = bun_hash_name(env->entries[position].name) & mask;
        while (table[slot] != -1) {
            slot = (slot + 1) & mask;
        }
        table[slot] = position;
    }
    env->table = table;
    env->table_size = size;
}

static int bun_env_find(BunEnv *env, const char *name) {
    size_t mask = (size_t)env->table_size - 1;
    size_t slot = bun_hash_name(name) & mask;
    while (env->table[slot] != -1) {
        BunBinding *binding = &env->entries[env->table[slot]];
        if (!binding->deleted && strcmp(binding->name, name) == 0) {
            return env->table[slot];
        }
        slot = (slot + 1) & mask;
    }
    return -1;
}

static void bun_env_set(BunEnv *env, const char *name, BunValue value,
                        int mutable) {
    int position = bun_env_find(env, name);
    if (position >= 0) {
        env->entries[position].value = value;
        env->entries[position].mutable = mutable;
        return;
    }
    if (env->count == env->cap) {
        env->cap = env->cap * 2;
        BunBinding *entries =
            (BunBinding *)bun_alloc(sizeof(BunBinding) * env->cap);
        memcpy(entries, env->entries, sizeof(BunBinding) * env->count);
        env->entries = entries;
    }
    env->entries[env->count].name = name;
    env->entries[env->count].value = value;
    env->entries[env->count].mutable = mutable;
    env->count++;
    if (env->count * 2 >= env->table_size) {
        bun_env_rehash(env, env->table_size * 2);
    } else {
        size_t mask = (size_t)env->table_size - 1;
        size_t slot = bun_hash_name(name) & mask;
        while (env->table[slot] != -1) {
            slot = (slot + 1) & mask;
        }
        env->table[slot] = env->count - 1;
    }
}

static BunValue bun_env_get(BunEnv *env, const char *name) {
    while (env) {
        int position = bun_env_find(env, name);
        if (position >= 0) {
            return env->entries[position].value;
        }
        env = env->parent;
    }
    bun_throw("undefined variable '%s'", name);
    return bun_null_value();
}

static void bun_env_define(BunEnv *env, const char *name, BunValue value,
                            int mutable) {
    /* A name holds a copy of the value, because a struct is a value
     * type: the program that holds the name and the program that made
     * the value do not share it. */
    bun_env_set(env, name, bun_copy_value(value), mutable);
}

static void bun_env_assign(BunEnv *env, const char *name, BunValue value) {
    while (env) {
        int position = bun_env_find(env, name);
        if (position >= 0) {
            if (!env->entries[position].mutable) {
                bun_throw("cannot assign to immutable variable '%s'", name);
            }
            env->entries[position].value = bun_copy_value(value);
            return;
        }
        env = env->parent;
    }
    bun_throw("undefined variable '%s'", name);
}

/* The `del` statement removes a name from the environment that holds it.
   The entry stays in the table, but it is marked, so the name is not
   found any more and the table keeps its shape. */
static void bun_env_delete(BunEnv *env, const char *name) {
    while (env) {
        int position = bun_env_find(env, name);
        if (position >= 0) {
            env->entries[position].deleted = 1;
            env->entries[position].value = bun_null_value();
            return;
        }
        env = env->parent;
    }
    bun_throw("undefined variable '%s'", name);
}

/* ------------------------------------------------------------------ */
/* The modules                                                         */
/* ------------------------------------------------------------------ */

/* A module is linked into the program of the backend: its body is a
   function of the program, and the values it exports live in a table.
   The table is filled while the body runs, so an export sees the value
   the name has at the place of the export. */

typedef struct {
    const char *name;
    BunValue value;
} BunExport;

typedef struct {
    BunExport *exports;
    int count;
    int cap;
} BunModule;

/* The env of the builtins.  A module reads the names it does not bind
   from there, like the module of the machine does. */
static BunEnv *bun_globals_env = NULL;

/* The module whose body is running.  Only one body runs at a time. */
static BunModule *bun_current_module = NULL;

static BunModule *bun_module_new(void) {
    BunModule *module = (BunModule *)bun_alloc(sizeof(BunModule));
    module->cap = 8;
    module->count = 0;
    module->exports = (BunExport *)bun_alloc(sizeof(BunExport) * module->cap);
    return module;
}

static void bun_module_export(const char *name, BunValue value) {
    if (!bun_current_module) {
        bun_throw("'export' is only allowed in modules");
    }
    BunModule *module = bun_current_module;
    if (module->count == module->cap) {
        module->cap = module->cap * 2;
        BunExport *exports =
            (BunExport *)bun_alloc(sizeof(BunExport) * module->cap);
        memcpy(exports, module->exports, sizeof(BunExport) * module->count);
        module->exports = exports;
    }
    module->exports[module->count].name = name;
    module->exports[module->count].value = value;
    module->count++;
}

static BunValue bun_module_lookup(BunModule *module, const char *name,
                                  const char *path) {
    for (int index = 0; index < module->count; index++) {
        if (strcmp(module->exports[index].name, name) == 0) {
            return module->exports[index].value;
        }
    }
    bun_throw("module '%s' does not export '%s'", path, name);
    return bun_null_value();
}

/* ------------------------------------------------------------------ */
/* The strings                                                         */
/* ------------------------------------------------------------------ */

static BunValue bun_str_new(const char *data, size_t len) {
    BunObj *object = bun_new_obj(BUN_STR);
    object->len = len;
    object->data = (char *)bun_alloc(len + 1);
    if (len) {
        memcpy(object->data, data, len);
    }
    object->data[len] = '\0';
    return bun_obj_value(object);
}

static BunValue bun_str_from_c(const char *text) {
    return bun_str_new(text, strlen(text));
}

static BunValue bun_str_concat(BunValue left, BunValue right) {
    BunObj *a = left.as.obj;
    BunObj *b = right.as.obj;
    size_t len = a->len + b->len;
    char *data = (char *)bun_alloc(len + 1);
    memcpy(data, a->data, a->len);
    memcpy(data + a->len, b->data, b->len);
    data[len] = '\0';
    BunObj *object = bun_new_obj(BUN_STR);
    object->len = len;
    object->data = data;
    return bun_obj_value(object);
}

/* ------------------------------------------------------------------ */
/* The structs                                                         */
/* ------------------------------------------------------------------ */

/* A struct is a value type.  The value of a struct is copied when it
 * is put in a name, when it is given to a function and when it is the
 * answer of a function, so two names never share one struct.  The copy
 * is deep: a struct that holds a struct holds a copy of it. */

static BunValue bun_copy_value(BunValue value) {
    if (value.tag != BUN_STRUCT) {
        return value;
    }
    BunObj *object = value.as.obj;
    size_t count = object->count;
    BunObj *copy = bun_new_obj(BUN_STRUCT);
    copy->name = object->name;
    copy->count = count;
    copy->cap = count;
    copy->field_names = object->field_names;
    copy->field_values =
        (BunValue *)bun_alloc(sizeof(BunValue) * (count ? count : 1));
    for (size_t index = 0; index < count; index++) {
        copy->field_values[index] = bun_copy_value(object->field_values[index]);
    }
    return bun_obj_value(copy);
}

static BunValue bun_struct_new(const char *type_name, const char **names,
                                BunValue *values, int count) {
    BunObj *object = bun_new_obj(BUN_STRUCT);
    object->name = type_name;
    object->count = (size_t)count;
    object->cap = (size_t)count;
    object->field_names =
        (const char **)bun_alloc(sizeof(char *) * (count ? count : 1));
    object->field_values =
        (BunValue *)bun_alloc(sizeof(BunValue) * (count ? count : 1));
    for (int index = 0; index < count; index++) {
        object->field_names[index] = names[index];
        object->field_values[index] = bun_copy_value(values[index]);
    }
    return bun_obj_value(object);
}

static int bun_struct_field(BunObj *object, const char *name) {
    for (size_t index = 0; index < object->count; index++) {
        if (strcmp(object->field_names[index], name) == 0) {
            return (int)index;
        }
    }
    return -1;
}

static BunValue bun_get_field(BunValue value, const char *name) {
    if (value.tag != BUN_STRUCT) {
        bun_throw("type '%s' has no field '%s'", bun_type_name(value), name);
    }
    BunObj *object = value.as.obj;
    int index = bun_struct_field(object, name);
    if (index < 0) {
        bun_throw("unknown field '%s' on %s", name, object->name);
    }
    return object->field_values[index];
}

static void bun_set_field(BunValue value, const char *name, BunValue field) {
    if (value.tag != BUN_STRUCT) {
        bun_throw("type '%s' has no field '%s'", bun_type_name(value), name);
    }
    BunObj *object = value.as.obj;
    int index = bun_struct_field(object, name);
    if (index < 0) {
        bun_throw("unknown field '%s' on %s", name, object->name);
    }
    object->field_values[index] = bun_copy_value(field);
}

/* The methods of the structs.  The table is filled when the program
 * runs an `impl` block, and the table of the machine is filled the same
 * way, so a method is found the same way under both. */

typedef struct BunStructMethod {
    const char *type_name;
    const char *method;
    BunFn fn;
    BunEnv *closure;
} BunStructMethod;

#define BUN_MAX_STRUCT_METHODS 256
static BunStructMethod bun_struct_methods[BUN_MAX_STRUCT_METHODS];
static int bun_struct_method_count = 0;

static void bun_register_struct_method(const char *type_name, const char *method,
                                        BunFn fn, BunEnv *closure) {
    for (int index = 0; index < bun_struct_method_count; index++) {
        BunStructMethod *entry = &bun_struct_methods[index];
        if (strcmp(entry->type_name, type_name) == 0 &&
            strcmp(entry->method, method) == 0) {
            entry->fn = fn;
            entry->closure = closure;
            return;
        }
    }
    if (bun_struct_method_count >= BUN_MAX_STRUCT_METHODS) {
        bun_throw("too many methods of structs");
    }
    BunStructMethod *entry = &bun_struct_methods[bun_struct_method_count++];
    entry->type_name = type_name;
    entry->method = method;
    entry->fn = fn;
    entry->closure = closure;
}

static BunFn bun_find_struct_method(const char *type_name, const char *method,
                                     BunEnv **closure) {
    for (int index = 0; index < bun_struct_method_count; index++) {
        BunStructMethod *entry = &bun_struct_methods[index];
        if (strcmp(entry->type_name, type_name) == 0 &&
            strcmp(entry->method, method) == 0) {
            if (closure != NULL) {
                *closure = entry->closure;
            }
            return entry->fn;
        }
    }
    return NULL;
}

/* ------------------------------------------------------------------ */
/* The lists and the dictionaries                                      */
/* ------------------------------------------------------------------ */

static BunValue bun_list_new(void) {
    BunObj *object = bun_new_obj(BUN_LIST);
    object->cap = 8;
    object->items = (BunValue *)bun_alloc(sizeof(BunValue) * object->cap);
    return bun_obj_value(object);
}

static void bun_list_push(BunObj *list, BunValue item) {
    if (list->count == list->cap) {
        list->cap = list->cap * 2;
        BunValue *items = (BunValue *)bun_alloc(sizeof(BunValue) * list->cap);
        memcpy(items, list->items, sizeof(BunValue) * list->count);
        list->items = items;
    }
    list->items[list->count] = item;
    list->count++;
}

/* The room of a list that is filled at once.  A list of a million
   items has its room at once, so the list does not grow while it is
   filled, and the memory of the program does not double. */
static void bun_list_reserve(BunObj *list, size_t count) {
    if (count <= list->cap) {
        return;
    }
    BunValue *items = (BunValue *)bun_alloc(sizeof(BunValue) * count);
    memcpy(items, list->items, sizeof(BunValue) * list->count);
    list->items = items;
    list->cap = count;
}

static BunValue bun_dict_new(void) {
    BunObj *object = bun_new_obj(BUN_DICT);
    object->cap = 8;
    object->keys = (BunValue *)bun_alloc(sizeof(BunValue) * object->cap);
    object->values = (BunValue *)bun_alloc(sizeof(BunValue) * object->cap);
    object->index_size = 16;
    object->index = (int *)bun_alloc(sizeof(int) * object->index_size);
    for (int index = 0; index < object->index_size; index++) {
        object->index[index] = -1;
    }
    return bun_obj_value(object);
}

static int bun_values_equal(BunValue left, BunValue right);
static double bun_as_double(BunValue value);

/* The hash of a key.  Two keys that are the same key have the same
 * hash, so that a lookup finds them: a number is hashed as the double
 * of its value, because a whole number and a float that are the same
 * number are the same key.  A key that is not a number is hashed by its
 * own shape, so that a boolean and a number never share a slot by
 * accident. */
static size_t bun_hash_value(BunValue value) {
    size_t hash = 1469598103934665603u;
    if (value.tag == BUN_STR) {
        BunObj *text = value.as.obj;
        for (size_t index = 0; index < text->len; index++) {
            hash ^= (unsigned char)text->data[index];
            hash *= 1099511628211u;
        }
        return hash;
    }
    if (value.tag == BUN_INT || value.tag == BUN_FLOAT) {
        double number = bun_as_double(value);
        if (number == 0.0) {
            number = 0.0;
        }
        const unsigned char *bytes = (const unsigned char *)&number;
        for (size_t index = 0; index < sizeof(double); index++) {
            hash ^= bytes[index];
            hash *= 1099511628211u;
        }
        return hash;
    }
    if (value.tag == BUN_BOOL) {
        hash ^= (size_t)(value.as.b ? 3 : 5);
        hash *= 1099511628211u;
        return hash;
    }
    hash ^= (size_t)11;
    hash *= 1099511628211u;
    return hash;
}

/* The table of the keys of a dictionary and the table of the values of
 * a set are open addressing tables, and the size of a table is always a
 * power of two, so the slot of a key is a mask and not a division.  A
 * division costs more than the rest of the lookup. */
static void bun_index_clear(int *table, int size) {
    for (int index = 0; index < size; index++) {
        table[index] = -1;
    }
}

static void bun_index_insert(int *table, int size, size_t hash,
                              int position) {
    size_t mask = (size_t)size - 1;
    size_t slot = hash & mask;
    while (table[slot] != -1) {
        slot = (slot + 1) & mask;
    }
    table[slot] = position;
}

/* A key of a dictionary is a number, a string, a boolean or null, the
 * same keys the machine accepts.  Any other value is a failure, and the
 * message is the message of the machine. */
static void bun_check_key(BunValue key) {
    if (key.tag == BUN_INT || key.tag == BUN_FLOAT || key.tag == BUN_STR ||
        key.tag == BUN_BOOL || key.tag == BUN_NULL) {
        return;
    }
    bun_throw("dict keys must be strings, numbers, or null");
}

/* The table of the keys is built again when a key is removed, because
 * the removal moves the keys of the dictionary and the table holds the
 * places of the keys. */
static void bun_dict_reindex(BunObj *dict) {
    bun_index_clear(dict->index, dict->index_size);
    for (size_t position = 0; position < dict->count; position++) {
        bun_index_insert(dict->index, dict->index_size,
                         bun_hash_value(dict->keys[position]),
                         (int)position);
    }
}

static void bun_dict_rehash(BunObj *dict, int size) {
    dict->index = (int *)bun_alloc(sizeof(int) * size);
    dict->index_size = size;
    bun_dict_reindex(dict);
}

static int bun_dict_find(BunObj *dict, BunValue key) {
    if (dict->count == 0) {
        return -1;
    }
    size_t mask = (size_t)dict->index_size - 1;
    size_t slot = bun_hash_value(key) & mask;
    while (dict->index[slot] != -1) {
        int position = dict->index[slot];
        if (bun_values_equal(dict->keys[position], key)) {
            return position;
        }
        slot = (slot + 1) & mask;
    }
    return -1;
}

static void bun_dict_set(BunObj *dict, BunValue key, BunValue value) {
    bun_check_key(key);
    int position = bun_dict_find(dict, key);
    if (position >= 0) {
        dict->values[position] = value;
        return;
    }
    if (dict->count == dict->cap) {
        dict->cap = dict->cap * 2;
        BunValue *keys = (BunValue *)bun_alloc(sizeof(BunValue) * dict->cap);
        BunValue *values =
            (BunValue *)bun_alloc(sizeof(BunValue) * dict->cap);
        memcpy(keys, dict->keys, sizeof(BunValue) * dict->count);
        memcpy(values, dict->values, sizeof(BunValue) * dict->count);
        dict->keys = keys;
        dict->values = values;
    }
    dict->keys[dict->count] = key;
    dict->values[dict->count] = value;
    dict->count++;
    if (dict->count * 2 >= dict->index_size) {
        bun_dict_rehash(dict, dict->index_size * 2);
    } else {
        bun_index_insert(dict->index, dict->index_size,
                         bun_hash_value(key), (int)dict->count - 1);
    }
}

static BunValue bun_dict_get(BunObj *dict, BunValue key) {
    bun_check_key(key);
    int position = bun_dict_find(dict, key);
    if (position < 0) {
        return bun_null_value();
    }
    return dict->values[position];
}

static int bun_dict_has(BunObj *dict, BunValue key) {
    bun_check_key(key);
    return bun_dict_find(dict, key) >= 0;
}

/* The value of a key that a name holds.  The name is a text of the
   program, and the hash of a text is the hash of its bytes, so the
   lookup of the name in the table of the keys is a hash and a probe. */
static BunValue bun_dict_get_c(BunObj *dict, const char *name) {
    if (dict->count == 0) {
        return bun_null_value();
    }
    size_t mask = (size_t)dict->index_size - 1;
    size_t slot = bun_hash_name(name) & mask;
    while (dict->index[slot] != -1) {
        int position = dict->index[slot];
        BunValue key = dict->keys[position];
        if (key.tag == BUN_STR && strcmp(key.as.obj->data, name) == 0) {
            return dict->values[position];
        }
        slot = (slot + 1) & mask;
    }
    return bun_null_value();
}

/* The method of a `with` target.  The target is a dictionary that holds
   the method, like the machine: a target that does not hold the method
   is a failure, and a method that is not a function is a failure too. */
static BunValue bun_protocol_get(BunValue target, const char *name) {
    BunValue method = bun_null_value();
    if (target.tag == BUN_DICT) {
        method = bun_dict_get_c(target.as.obj, name);
    }
    if (method.tag == BUN_NULL) {
        bun_throw("'with' target does not implement '%s'", name);
    }
    if (method.tag != BUN_FUNC && method.tag != BUN_BUILTIN) {
        bun_throw("'with' target method '%s' is not callable", name);
    }
    return method;
}

static void bun_dict_remove(BunObj *dict, BunValue key) {
    bun_check_key(key);
    int position = bun_dict_find(dict, key);
    if (position < 0) {
        bun_throw("key not found");
    }
    for (size_t index = (size_t)position; index + 1 < dict->count; index++) {
        dict->keys[index] = dict->keys[index + 1];
        dict->values[index] = dict->values[index + 1];
    }
    dict->count--;
    bun_dict_reindex(dict);
}

/* ------------------------------------------------------------------ */
/* The sets                                                             */
/* ------------------------------------------------------------------ */

/* A set holds the values that are not equal to each other, and it keeps
 * the order the values came in, so a set prints its values the way they
 * were added.  The values of a set are the values a dictionary accepts as
 * a key: a number, a string, a boolean or null. */
static BunValue bun_set_new(void) {
    BunObj *object = bun_new_obj(BUN_SET);
    object->cap = 8;
    object->items = (BunValue *)bun_alloc(sizeof(BunValue) * object->cap);
    object->index_size = 16;
    object->index = (int *)bun_alloc(sizeof(int) * object->index_size);
    for (int index = 0; index < object->index_size; index++) {
        object->index[index] = -1;
    }
    return bun_obj_value(object);
}

/* The table of the values of a set is built again when a value is
 * removed, because the removal moves the values of the set and the table
 * holds the places of the values. */
static void bun_set_reindex(BunObj *set) {
    bun_index_clear(set->index, set->index_size);
    for (size_t position = 0; position < set->count; position++) {
        bun_index_insert(set->index, set->index_size,
                         bun_hash_value(set->items[position]),
                         (int)position);
    }
}

static void bun_set_rehash(BunObj *set, int size) {
    set->index = (int *)bun_alloc(sizeof(int) * size);
    set->index_size = size;
    bun_set_reindex(set);
}

static int bun_set_find(BunObj *set, BunValue item) {
    if (set->count == 0) {
        return -1;
    }
    size_t mask = (size_t)set->index_size - 1;
    size_t slot = bun_hash_value(item) & mask;
    while (set->index[slot] != -1) {
        int position = set->index[slot];
        if (bun_values_equal(set->items[position], item)) {
            return position;
        }
        slot = (slot + 1) & mask;
    }
    return -1;
}

static void bun_set_add(BunObj *set, BunValue item) {
    bun_check_key(item);
    int position = bun_set_find(set, item);
    if (position >= 0) {
        /* A value that is already in the set keeps its place and takes the
           new value, the way the machine does. */
        set->items[position] = item;
        return;
    }
    if (set->count == set->cap) {
        set->cap = set->cap * 2;
        BunValue *items = (BunValue *)bun_alloc(sizeof(BunValue) * set->cap);
        memcpy(items, set->items, sizeof(BunValue) * set->count);
        set->items = items;
    }
    set->items[set->count] = item;
    set->count++;
    if (set->count * 2 >= set->index_size) {
        bun_set_rehash(set, set->index_size * 2);
    } else {
        bun_index_insert(set->index, set->index_size,
                         bun_hash_value(item), (int)set->count - 1);
    }
}

static void bun_set_remove(BunObj *set, BunValue item) {
    bun_check_key(item);
    int position = bun_set_find(set, item);
    if (position < 0) {
        bun_throw("value not in set");
    }
    for (size_t index = (size_t)position; index + 1 < set->count; index++) {
        set->items[index] = set->items[index + 1];
    }
    set->count--;
    bun_set_reindex(set);
}

static BunValue bun_set_values(BunObj *set) {
    BunValue list = bun_list_new();
    bun_list_reserve(list.as.obj, set->count);
    for (size_t index = 0; index < set->count; index++) {
        bun_list_push(list.as.obj, set->items[index]);
    }
    return list;
}

static BunValue bun_set_union(BunObj *left, BunObj *right) {
    BunValue result = bun_set_new();
    for (size_t index = 0; index < left->count; index++) {
        bun_set_add(result.as.obj, left->items[index]);
    }
    for (size_t index = 0; index < right->count; index++) {
        bun_set_add(result.as.obj, right->items[index]);
    }
    return result;
}

static BunValue bun_set_intersection(BunObj *left, BunObj *right) {
    BunValue result = bun_set_new();
    for (size_t index = 0; index < left->count; index++) {
        if (bun_set_find(right, left->items[index]) >= 0) {
            bun_set_add(result.as.obj, left->items[index]);
        }
    }
    return result;
}

static BunValue bun_set_difference(BunObj *left, BunObj *right) {
    BunValue result = bun_set_new();
    for (size_t index = 0; index < left->count; index++) {
        if (bun_set_find(right, left->items[index]) < 0) {
            bun_set_add(result.as.obj, left->items[index]);
        }
    }
    return result;
}

static BunValue bun_builtin_set(BunValue *args, int count) {
    if (count > 1) {
        bun_throw("set() expects 0 or 1 arguments, got %d", count);
    }
    BunValue result = bun_set_new();
    if (count == 0) {
        return result;
    }
    if (args[0].tag != BUN_LIST) {
        bun_throw("set() expects a list");
    }
    BunObj *list = args[0].as.obj;
    for (size_t index = 0; index < list->count; index++) {
        bun_set_add(result.as.obj, list->items[index]);
    }
    return result;
}

/* ------------------------------------------------------------------ */
/* The secrets                                                         */
/* ------------------------------------------------------------------ */

/* A secret is a value that is masked in every rendering.  The value it
   holds is only reachable through the method `reveal`, which keeps the
   way out of the secret easy to find. */
#define BUN_SECRET_MASK "***"

static BunValue bun_secret_new(BunValue value) {
    BunObj *object = bun_new_obj(BUN_SECRET);
    object->secret = value;
    return bun_obj_value(object);
}

static BunValue bun_builtin_secret(BunValue *args, int count) {
    if (count != 1) {
        bun_throw("secret() expects 1 argument, got %d", count);
    }
    return bun_secret_new(args[0]);
}

/* The `del` statement removes an item from a dict or from a list.  The
   failures are the failures of the machine, word for word. */
static void bun_delete_index(BunValue obj, BunValue index) {
    if (obj.tag == BUN_DICT) {
        bun_dict_remove(obj.as.obj, index);
        return;
    }
    if (obj.tag != BUN_LIST) {
        bun_throw("can only delete from a list or a dict");
    }
    if (index.tag != BUN_INT) {
        bun_throw("list index must be an integer");
    }
    BunObj *list = obj.as.obj;
    int64_t position = index.as.i;
    if (position < 0 || position >= (int64_t)list->count) {
        bun_throw("list index %lld out of range", (long long)position);
    }
    for (size_t at = (size_t)position; at + 1 < list->count; at++) {
        list->items[at] = list->items[at + 1];
    }
    list->count--;
}

/* ------------------------------------------------------------------ */
/* The truth, the equality and the printing                            */
/* ------------------------------------------------------------------ */

static int bun_truthy(BunValue value) {
    switch (value.tag) {
    case BUN_NULL:
        return 0;
    case BUN_BOOL:
        return value.as.b ? 1 : 0;
    case BUN_INT:
        return value.as.i != 0;
    case BUN_FLOAT:
        return value.as.f != 0.0;
    case BUN_STR:
        return value.as.obj->len != 0;
    case BUN_LIST:
        return value.as.obj->count != 0;
    default:
        return 1;
    }
}

static int bun_is_number(BunValue value) {
    return value.tag == BUN_INT || value.tag == BUN_FLOAT;
}

static double bun_as_double(BunValue value) {
    if (value.tag == BUN_INT) {
        return (double)value.as.i;
    }
    return value.as.f;
}

static int bun_values_equal_slow(BunValue left, BunValue right);

/* The equality has a fast path for the two whole numbers and for the
   two empty values, and the fast path is inlined into the program. */
static inline int bun_values_equal(BunValue left, BunValue right) {
    if (left.tag == BUN_INT && right.tag == BUN_INT) {
        return left.as.i == right.as.i;
    }
    if (left.tag == BUN_NULL || right.tag == BUN_NULL) {
        return left.tag == BUN_NULL && right.tag == BUN_NULL;
    }
    return bun_values_equal_slow(left, right);
}

static int bun_values_equal_slow(BunValue left, BunValue right) {
    if (left.tag == BUN_SECRET || right.tag == BUN_SECRET) {
        /* Two secrets are the same secret when the values they hold are
           the same value, and a secret is never the same value as
           something that is not a secret. */
        if (left.tag != BUN_SECRET || right.tag != BUN_SECRET) {
            return 0;
        }
        return bun_values_equal(left.as.obj->secret, right.as.obj->secret);
    }
    if (left.tag == BUN_BOOL || right.tag == BUN_BOOL) {
        if (left.tag != BUN_BOOL || right.tag != BUN_BOOL) {
            return 0;
        }
        return left.as.b == right.as.b;
    }
    if (left.tag == BUN_NULL || right.tag == BUN_NULL) {
        return left.tag == BUN_NULL && right.tag == BUN_NULL;
    }
    if (bun_is_number(left) && bun_is_number(right)) {
        if (left.tag == BUN_INT && right.tag == BUN_INT) {
            return left.as.i == right.as.i;
        }
        return bun_as_double(left) == bun_as_double(right);
    }
    if (left.tag == BUN_STR && right.tag == BUN_STR) {
        BunObj *a = left.as.obj;
        BunObj *b = right.as.obj;
        return a->len == b->len && memcmp(a->data, b->data, a->len) == 0;
    }
    if (left.tag == BUN_LIST && right.tag == BUN_LIST) {
        BunObj *a = left.as.obj;
        BunObj *b = right.as.obj;
        if (a->count != b->count) {
            return 0;
        }
        for (size_t index = 0; index < a->count; index++) {
            if (!bun_values_equal(a->items[index], b->items[index])) {
                return 0;
            }
        }
        return 1;
    }
    if (left.tag == BUN_DICT && right.tag == BUN_DICT) {
        BunObj *a = left.as.obj;
        BunObj *b = right.as.obj;
        if (a->count != b->count) {
            return 0;
        }
        for (size_t index = 0; index < a->count; index++) {
            if (!bun_dict_has(b, a->keys[index])) {
                return 0;
            }
            if (!bun_values_equal(a->values[index],
                                  bun_dict_get(b, a->keys[index]))) {
                return 0;
            }
        }
        return 1;
    }
    if (left.tag == BUN_SET && right.tag == BUN_SET) {
        BunObj *a = left.as.obj;
        BunObj *b = right.as.obj;
        if (a->count != b->count) {
            return 0;
        }
        for (size_t index = 0; index < a->count; index++) {
            if (bun_set_find(b, a->items[index]) < 0) {
                return 0;
            }
        }
        return 1;
    }
    if (left.tag == BUN_STRUCT || right.tag == BUN_STRUCT) {
        if (left.tag != BUN_STRUCT || right.tag != BUN_STRUCT) {
            return 0;
        }
        BunObj *a = left.as.obj;
        BunObj *b = right.as.obj;
        if (strcmp(a->name, b->name) != 0 || a->count != b->count) {
            return 0;
        }
        for (size_t index = 0; index < a->count; index++) {
            if (strcmp(a->field_names[index], b->field_names[index]) != 0) {
                return 0;
            }
            if (!bun_values_equal(a->field_values[index],
                                  b->field_values[index])) {
                return 0;
            }
        }
        return 1;
    }
    return 0;
}

/* The text of a float, the way Python prints it: the shortest text that
 * reads back to the same float. */
static void bun_format_float(char *out, size_t size, double number) {
    /* The format of a float is the one of the runtime: the shortest text
       that reads back to the same number, the exponential form only when
       the exponent is small or large, and the ".0" of a whole number. */
    if (number != number) {
        snprintf(out, size, "nan");
        return;
    }
    if (number > 1.7976931348623157e308) {
        snprintf(out, size, "inf");
        return;
    }
    if (number < -1.7976931348623157e308) {
        snprintf(out, size, "-inf");
        return;
    }

    char buffer[64];
    int digits = 17;
    for (int precision = 1; precision <= 17; precision++) {
        snprintf(buffer, sizeof(buffer), "%.*e", precision - 1, number);
        if (strtod(buffer, NULL) == number) {
            digits = precision;
            break;
        }
    }

    const char *marker = strchr(buffer, 'e');
    int exponent = marker ? atoi(marker + 1) : 0;

    if (exponent < -4 || exponent >= 16) {
        /* The exponential form: 1e+16, 1.5e+20, 1e-05. */
        char mantissa[64];
        size_t length = 0;
        for (const char *at = buffer; *at && *at != 'e'; at++) {
            mantissa[length++] = *at;
        }
        mantissa[length] = '\0';
        if (strchr(mantissa, '.')) {
            while (length > 0 && mantissa[length - 1] == '0') {
                length--;
            }
            if (length > 0 && mantissa[length - 1] == '.') {
                length--;
            }
            mantissa[length] = '\0';
        }
        snprintf(out, size, "%se%s%02d", mantissa, exponent < 0 ? "-" : "+",
                 exponent < 0 ? -exponent : exponent);
        return;
    }

    int decimals = digits - 1 - exponent;
    if (decimals < 0) {
        decimals = 0;
    }
    snprintf(out, size, "%.*f", decimals, number);
    if (!strpbrk(out, ".eEn")) {
        size_t length = strlen(out);
        if (length + 3 < size) {
            out[length] = '.';
            out[length + 1] = '0';
            out[length + 2] = '\0';
        }
    }
}

/* The text of a value, the way the runtime prints it. */
static char *bun_stringify(BunValue value) {
    switch (value.tag) {
    case BUN_NULL:
        return "null";
    case BUN_BOOL:
        return value.as.b ? "true" : "false";
    case BUN_INT: {
        char *out = (char *)bun_alloc(64);
        snprintf(out, 64, "%lld", (long long)value.as.i);
        return out;
    }
    case BUN_FLOAT: {
        char *out = (char *)bun_alloc(64);
        bun_format_float(out, 64, value.as.f);
        return out;
    }
    case BUN_STR:
        return value.as.obj->data;
    case BUN_SECRET:
        return BUN_SECRET_MASK;
    case BUN_LIST: {
        BunObj *list = value.as.obj;
        size_t size = 2;
        for (size_t index = 0; index < list->count; index++) {
            size += strlen(bun_stringify(list->items[index])) + 2;
        }
        char *out = (char *)bun_alloc(size);
        size_t at = 0;
        out[at++] = '[';
        for (size_t index = 0; index < list->count; index++) {
            if (index) {
                out[at++] = ',';
                out[at++] = ' ';
            }
            const char *text = bun_stringify(list->items[index]);
            size_t len = strlen(text);
            memcpy(out + at, text, len);
            at += len;
        }
        out[at++] = ']';
        out[at] = '\0';
        return out;
    }
    case BUN_DICT: {
        BunObj *dict = value.as.obj;
        size_t size = 2;
        for (size_t index = 0; index < dict->count; index++) {
            size += strlen(bun_stringify(dict->keys[index])) +
                    strlen(bun_stringify(dict->values[index])) + 4;
        }
        char *out = (char *)bun_alloc(size);
        size_t at = 0;
        out[at++] = '{';
        for (size_t index = 0; index < dict->count; index++) {
            if (index) {
                out[at++] = ',';
                out[at++] = ' ';
            }
            const char *key = bun_stringify(dict->keys[index]);
            size_t len = strlen(key);
            memcpy(out + at, key, len);
            at += len;
            out[at++] = ':';
            out[at++] = ' ';
            const char *item = bun_stringify(dict->values[index]);
            len = strlen(item);
            memcpy(out + at, item, len);
            at += len;
        }
        out[at++] = '}';
        out[at] = '\0';
        return out;
    }
    case BUN_SET: {
        BunObj *set = value.as.obj;
        size_t size = 2;
        for (size_t index = 0; index < set->count; index++) {
            size += strlen(bun_stringify(set->items[index])) + 2;
        }
        char *out = (char *)bun_alloc(size);
        size_t at = 0;
        out[at++] = '{';
        for (size_t index = 0; index < set->count; index++) {
            if (index) {
                out[at++] = ',';
                out[at++] = ' ';
            }
            const char *item = bun_stringify(set->items[index]);
            size_t len = strlen(item);
            memcpy(out + at, item, len);
            at += len;
        }
        out[at++] = '}';
        out[at] = '\0';
        return out;
    }
    case BUN_FUNC: {
        char *out = (char *)bun_alloc(64);
        snprintf(out, 64, "<fn %s>", value.as.obj->name);
        return out;
    }
    case BUN_BUILTIN: {
        char *out = (char *)bun_alloc(64);
        snprintf(out, 64, "<builtin %s>", value.as.obj->name);
        return out;
    }
    case BUN_STRUCT: {
        BunObj *object = value.as.obj;
        size_t size = strlen(object->name) + 3;
        for (size_t index = 0; index < object->count; index++) {
            size += strlen(object->field_names[index]) +
                    strlen(bun_stringify(object->field_values[index])) + 4;
        }
        char *out = (char *)bun_alloc(size);
        size_t at = 0;
        size_t len = strlen(object->name);
        memcpy(out + at, object->name, len);
        at += len;
        out[at++] = '{';
        for (size_t index = 0; index < object->count; index++) {
            if (index) {
                out[at++] = ',';
                out[at++] = ' ';
            }
            len = strlen(object->field_names[index]);
            memcpy(out + at, object->field_names[index], len);
            at += len;
            out[at++] = ':';
            out[at++] = ' ';
            const char *item = bun_stringify(object->field_values[index]);
            len = strlen(item);
            memcpy(out + at, item, len);
            at += len;
        }
        out[at++] = '}';
        out[at] = '\0';
        return out;
    }
    }
    return "null";
}

/* The text of a value, the way the `!r` conversion prints it. */
static char *bun_repr(BunValue value) {
    if (value.tag == BUN_SECRET) {
        return BUN_SECRET_MASK;
    }
    if (value.tag == BUN_STR) {
        BunObj *text = value.as.obj;
        size_t size = text->len * 2 + 3;
        char *out = (char *)bun_alloc(size);
        size_t at = 0;
        out[at++] = '"';
        for (size_t index = 0; index < text->len; index++) {
            char char_ = text->data[index];
            if (char_ == '"' || char_ == '\\') {
                out[at++] = '\\';
                out[at++] = char_;
            } else if (char_ == '\n') {
                out[at++] = '\\';
                out[at++] = 'n';
            } else if (char_ == '\t') {
                out[at++] = '\\';
                out[at++] = 't';
            } else if (char_ == '\r') {
                out[at++] = '\\';
                out[at++] = 'r';
            } else {
                out[at++] = char_;
            }
        }
        out[at++] = '"';
        out[at] = '\0';
        return out;
    }
    if (value.tag == BUN_LIST) {
        BunObj *list = value.as.obj;
        size_t size = 2;
        for (size_t index = 0; index < list->count; index++) {
            size += strlen(bun_repr(list->items[index])) + 2;
        }
        char *out = (char *)bun_alloc(size);
        size_t at = 0;
        out[at++] = '[';
        for (size_t index = 0; index < list->count; index++) {
            if (index) {
                out[at++] = ',';
                out[at++] = ' ';
            }
            const char *text = bun_repr(list->items[index]);
            size_t len = strlen(text);
            memcpy(out + at, text, len);
            at += len;
        }
        out[at++] = ']';
        out[at] = '\0';
        return out;
    }
    if (value.tag == BUN_DICT) {
        BunObj *dict = value.as.obj;
        size_t size = 2;
        for (size_t index = 0; index < dict->count; index++) {
            size += strlen(bun_repr(dict->keys[index])) +
                    strlen(bun_repr(dict->values[index])) + 4;
        }
        char *out = (char *)bun_alloc(size);
        size_t at = 0;
        out[at++] = '{';
        for (size_t index = 0; index < dict->count; index++) {
            if (index) {
                out[at++] = ',';
                out[at++] = ' ';
            }
            const char *key = bun_repr(dict->keys[index]);
            size_t len = strlen(key);
            memcpy(out + at, key, len);
            at += len;
            out[at++] = ':';
            out[at++] = ' ';
            const char *item = bun_repr(dict->values[index]);
            len = strlen(item);
            memcpy(out + at, item, len);
            at += len;
        }
        out[at++] = '}';
        out[at] = '\0';
        return out;
    }
    if (value.tag == BUN_SET) {
        BunObj *set = value.as.obj;
        size_t size = 2;
        for (size_t index = 0; index < set->count; index++) {
            size += strlen(bun_repr(set->items[index])) + 2;
        }
        char *out = (char *)bun_alloc(size);
        size_t at = 0;
        out[at++] = '{';
        for (size_t index = 0; index < set->count; index++) {
            if (index) {
                out[at++] = ',';
                out[at++] = ' ';
            }
            const char *item = bun_repr(set->items[index]);
            size_t len = strlen(item);
            memcpy(out + at, item, len);
            at += len;
        }
        out[at++] = '}';
        out[at] = '\0';
        return out;
    }
    if (value.tag == BUN_STRUCT) {
        BunObj *object = value.as.obj;
        size_t size = strlen(object->name) + 3;
        for (size_t index = 0; index < object->count; index++) {
            size += strlen(object->field_names[index]) +
                    strlen(bun_repr(object->field_values[index])) + 4;
        }
        char *out = (char *)bun_alloc(size);
        size_t at = 0;
        size_t len = strlen(object->name);
        memcpy(out + at, object->name, len);
        at += len;
        out[at++] = '{';
        for (size_t index = 0; index < object->count; index++) {
            if (index) {
                out[at++] = ',';
                out[at++] = ' ';
            }
            len = strlen(object->field_names[index]);
            memcpy(out + at, object->field_names[index], len);
            at += len;
            out[at++] = ':';
            out[at++] = ' ';
            const char *item = bun_repr(object->field_values[index]);
            len = strlen(item);
            memcpy(out + at, item, len);
            at += len;
        }
        out[at++] = '}';
        out[at] = '\0';
        return out;
    }
    return bun_stringify(value);
}

/* The name of a type in a message of an error.  A list is a list, and a
   function is a function. */
static const char *bun_type_name(BunValue value) {
    switch (value.tag) {
    case BUN_NULL:
        return "null";
    case BUN_BOOL:
        return "bool";
    case BUN_INT:
        return "int";
    case BUN_FLOAT:
        return "float";
    case BUN_STR:
        return "string";
    case BUN_LIST:
        return "list";
    case BUN_DICT:
        return "dict";
    case BUN_SET:
        return "set";
    case BUN_FUNC:
        return "function";
    case BUN_BUILTIN:
        return "builtin";
    case BUN_SECRET:
        return "secret";
    case BUN_STRUCT:
        return value.as.obj->name;
    }
    return "value";
}

/* The name of a type in the answer of the builtin 'type_of'.  The
   machine names a list an array and a function a fn, and the backend
   names them the same way, so that a program prints the same under both.
   A builtin of the language is a function of the machine and not a
   function of the program, and the machine has no name for it. */
static const char *bun_public_type_name(BunValue value) {
    switch (value.tag) {
    case BUN_NULL:
        return "null";
    case BUN_BOOL:
        return "bool";
    case BUN_INT:
        return "int";
    case BUN_FLOAT:
        return "float";
    case BUN_STR:
        return "string";
    case BUN_LIST:
        return "array";
    case BUN_DICT:
        return "dict";
    case BUN_SET:
        return "set";
    case BUN_FUNC:
        return "fn";
    case BUN_BUILTIN:
        return "any";
    case BUN_SECRET:
        return "secret";
    case BUN_STRUCT:
        return "any";
    }
    return "any";
}

/* ------------------------------------------------------------------ */
/* The canonical dump                                                  */
/* ------------------------------------------------------------------ */

/* The text of a dump grows while it is built, and the arena of the
   runtime never gives a block back, so the buffer grows by copying. */
typedef struct BunText {
    char *data;
    size_t len;
    size_t cap;
} BunText;

static void bun_text_add(BunText *text, const char *piece) {
    size_t len = strlen(piece);
    if (text->len + len + 1 > text->cap) {
        size_t cap = text->cap ? text->cap * 2 : 128;
        while (cap < text->len + len + 1) {
            cap *= 2;
        }
        char *data = (char *)bun_alloc(cap);
        if (text->data) {
            memcpy(data, text->data, text->len);
        }
        text->data = data;
        text->cap = cap;
    }
    memcpy(text->data + text->len, piece, len);
    text->len += len;
    text->data[text->len] = '\0';
}

static void bun_text_add_char(BunText *text, char piece) {
    char buffer[2];
    buffer[0] = piece;
    buffer[1] = '\0';
    bun_text_add(text, buffer);
}

/* A pair of a dictionary, the text of its key and the text of its
   value.  The pairs of a dictionary are sorted by the text of the key,
   and the machine sorts them the same way. */
typedef struct BunPair {
    const char *key;
    const char *value;
} BunPair;

static int bun_pair_compare(const void *left, const void *right) {
    const BunPair *a = (const BunPair *)left;
    const BunPair *b = (const BunPair *)right;
    int order = strcmp(a->key, b->key);
    if (order != 0) {
        return order;
    }
    return strcmp(a->value, b->value);
}

static void bun_dump_into(BunText *text, BunValue value);

static char *bun_canonical_dump(BunValue value) {
    BunText text;
    text.data = NULL;
    text.len = 0;
    text.cap = 0;
    bun_dump_into(&text, value);
    return text.data;
}

static void bun_dump_into(BunText *text, BunValue value) {
    switch (value.tag) {
    case BUN_NULL:
        bun_text_add(text, "null");
        return;
    case BUN_BOOL:
        bun_text_add(text, value.as.b ? "true" : "false");
        return;
    case BUN_INT: {
        char buffer[32];
        snprintf(buffer, sizeof(buffer), "%lld", (long long)value.as.i);
        bun_text_add(text, buffer);
        return;
    }
    case BUN_FLOAT: {
        char buffer[64];
        bun_format_float(buffer, sizeof(buffer), value.as.f);
        bun_text_add(text, buffer);
        return;
    }
    case BUN_STR:
        bun_text_add(text, bun_repr(value));
        return;
    case BUN_SECRET:
        bun_text_add(text, "\"" BUN_SECRET_MASK "\"");
        return;
    case BUN_LIST: {
        BunObj *list = value.as.obj;
        bun_text_add_char(text, '[');
        for (size_t index = 0; index < list->count; index++) {
            if (index) {
                bun_text_add(text, ", ");
            }
            bun_dump_into(text, list->items[index]);
        }
        bun_text_add_char(text, ']');
        return;
    }
    case BUN_SET: {
        BunObj *set = value.as.obj;
        bun_text_add_char(text, '[');
        for (size_t index = 0; index < set->count; index++) {
            if (index) {
                bun_text_add(text, ", ");
            }
            bun_dump_into(text, set->items[index]);
        }
        bun_text_add_char(text, ']');
        return;
    }
    case BUN_DICT: {
        BunObj *dict = value.as.obj;
        size_t count = dict->count;
        BunPair *pairs = NULL;
        if (count) {
            pairs = (BunPair *)bun_alloc(sizeof(BunPair) * count);
        }
        for (size_t index = 0; index < count; index++) {
            pairs[index].key = bun_canonical_dump(dict->keys[index]);
            pairs[index].value = bun_canonical_dump(dict->values[index]);
        }
        if (count > 1) {
            qsort(pairs, count, sizeof(BunPair), bun_pair_compare);
        }
        bun_text_add_char(text, '{');
        for (size_t index = 0; index < count; index++) {
            if (index) {
                bun_text_add(text, ", ");
            }
            bun_text_add(text, pairs[index].key);
            bun_text_add(text, ": ");
            bun_text_add(text, pairs[index].value);
        }
        bun_text_add_char(text, '}');
        return;
    }
    case BUN_FUNC:
        bun_throw("cannot canonicalize BunFunction");
        return;
    case BUN_BUILTIN:
        bun_throw("cannot canonicalize Builtin");
        return;
    }
    bun_throw("cannot canonicalize value");
}

static BunValue bun_builtin_dump(BunValue *args, int count) {
    if (count != 1) {
        bun_throw("dump() expects 1 argument, got %d", count);
    }
    return bun_str_from_c(bun_canonical_dump(args[0]));
}

static BunValue bun_builtin_Ok(BunValue *args, int count) {
    if (count != 1) {
        bun_throw("Ok() expects 1 argument");
    }
    BunValue result = bun_dict_new();
    bun_dict_set(result.as.obj, bun_str_from_c("ok"), args[0]);
    return result;
}

static BunValue bun_builtin_Err(BunValue *args, int count) {
    if (count != 1) {
        bun_throw("Err() expects 1 argument");
    }
    BunValue result = bun_dict_new();
    bun_dict_set(result.as.obj, bun_str_from_c("err"), args[0]);
    return result;
}

static BunValue bun_builtin_is_ok(BunValue *args, int count) {
    if (count != 1) {
        bun_throw("is_ok() expects 1 argument");
    }
    if (args[0].tag != BUN_DICT) {
        return bun_bool_value(0);
    }
    return bun_bool_value(bun_dict_has(args[0].as.obj, bun_str_from_c("ok")));
}

static BunValue bun_builtin_is_err(BunValue *args, int count) {
    if (count != 1) {
        bun_throw("is_err() expects 1 argument");
    }
    if (args[0].tag != BUN_DICT) {
        return bun_bool_value(0);
    }
    BunObj *dict = args[0].as.obj;
    return bun_bool_value(bun_dict_has(dict, bun_str_from_c("err"))
                         && !bun_dict_has(dict, bun_str_from_c("ok")));
}

/* The builtins of an option: `some(v)` is an option that carries a
   value, `none()` is an option that carries nothing, and the two `is_`
   builtins report which one it is without taking the value apart. */
static BunValue bun_builtin_some(BunValue *args, int count) {
    if (count != 1) {
        bun_throw("some() expects 1 argument");
    }
    BunValue option = bun_dict_new();
    bun_dict_set(option.as.obj, bun_str_from_c("some"), args[0]);
    return option;
}

static BunValue bun_builtin_none(BunValue *args, int count) {
    if (count != 0) {
        bun_throw("none() expects no argument");
    }
    (void)args;
    BunValue option = bun_dict_new();
    bun_dict_set(option.as.obj, bun_str_from_c("none"), bun_null_value());
    return option;
}

static BunValue bun_builtin_is_some(BunValue *args, int count) {
    if (count != 1) {
        bun_throw("is_some() expects 1 argument");
    }
    if (args[0].tag != BUN_DICT) {
        return bun_bool_value(0);
    }
    return bun_bool_value(bun_dict_has(args[0].as.obj, bun_str_from_c("some")));
}

static BunValue bun_builtin_is_none(BunValue *args, int count) {
    if (count != 1) {
        bun_throw("is_none() expects 1 argument");
    }
    if (args[0].tag != BUN_DICT) {
        return bun_bool_value(0);
    }
    return bun_bool_value(bun_dict_has(args[0].as.obj, bun_str_from_c("none")));
}

/* Take the payload of a Result or of an option, or hand it back.
   A Result is a dict with an `ok` key or an `err` key, and an option is
   a dict with a `some` key or a `none` key.  The payload key wins when
   the dict has one, so `Ok` wins over `Err` and `some` wins over `none`.
   A value that is neither is an error.  The return is 1 when `out` holds
   the unwrapped value, and 0 when the caller has to return the value
   itself, so a `?` on a value that carries nothing gives it back to the
   caller. */
static int bun_unwrap_result(BunValue value, BunValue *out) {
    if (value.tag != BUN_DICT) {
        bun_throw("'?' expects a Result or an option value, got %s", bun_public_type_name(value));
    }
    if (bun_dict_has(value.as.obj, bun_str_from_c("ok"))) {
        *out = bun_dict_get_c(value.as.obj, "ok");
        return 1;
    }
    if (bun_dict_has(value.as.obj, bun_str_from_c("some"))) {
        *out = bun_dict_get_c(value.as.obj, "some");
        return 1;
    }
    if (bun_dict_has(value.as.obj, bun_str_from_c("err"))) {
        return 0;
    }
    if (bun_dict_has(value.as.obj, bun_str_from_c("none"))) {
        return 0;
    }
    bun_throw("'?' expects a Result or an option value");
    return 0;
}

/* ------------------------------------------------------------------ */
/* The arithmetic                                                      */
/* ------------------------------------------------------------------ */

/* The integers of the language are 64 bits wide, in every engine.  An
 * operation that leaves the range is an error and not a number that
 * wraps around, so that a program behaves the same under the machine
 * and under the backend. */
#define BUN_INT_MIN (-9223372036854775807LL - 1)
#define BUN_INT_MAX 9223372036854775807LL

static int64_t bun_int_overflow(void) {
    bun_throw("integer overflow");
    return 0;
}

static int64_t bun_add_int(int64_t a, int64_t b) {
    int64_t result;
    if (__builtin_add_overflow(a, b, &result)) {
        return bun_int_overflow();
    }
    return result;
}

static int64_t bun_sub_int(int64_t a, int64_t b) {
    int64_t result;
    if (__builtin_sub_overflow(a, b, &result)) {
        return bun_int_overflow();
    }
    return result;
}

static int64_t bun_mul_int(int64_t a, int64_t b) {
    int64_t result;
    if (__builtin_mul_overflow(a, b, &result)) {
        return bun_int_overflow();
    }
    return result;
}

/* The remainder of the division of two whole numbers, the way the
   machine does it: the rest has the sign of the divisor.  The smallest
   number divided by minus one is zero, and the machine of the system
   cannot compute it. */
static int64_t bun_mod_int(int64_t a, int64_t b) {
    if (a == BUN_INT_MIN && b == -1) {
        return 0;
    }
    int64_t rest = a % b;
    if (rest != 0 && ((rest < 0) != (b < 0))) {
        rest += b;
    }
    return rest;
}

static int64_t bun_shl_int(int64_t a, int64_t b) {
    if (b >= 63) {
        if (a == 0) {
            return 0;
        }
        return bun_int_overflow();
    }
    int64_t result = a << b;
    if (a != 0 && (result >> b) != a) {
        return bun_int_overflow();
    }
    return result;
}

static int64_t bun_shr_int(int64_t a, int64_t b) {
    if (b >= 63) {
        return a < 0 ? -1 : 0;
    }
    return a >> b;
}

static BunValue bun_add_slow(BunValue left, BunValue right);

/* The arithmetic has a fast path for the two whole numbers, and the
   fast path is inlined into the program.  The slow path holds the
   strings, the lists and the failures, and it stays out of the line. */
static inline BunValue bun_add(BunValue left, BunValue right) {
    if (left.tag == BUN_INT && right.tag == BUN_INT) {
        return bun_int_value(bun_add_int(left.as.i, right.as.i));
    }
    return bun_add_slow(left, right);
}

static BunValue bun_add_slow(BunValue left, BunValue right) {
    if (left.tag == BUN_STR && right.tag == BUN_STR) {
        return bun_str_concat(left, right);
    }
    if (left.tag == BUN_LIST && right.tag == BUN_LIST) {
        BunValue result = bun_list_new();
        BunObj *a = left.as.obj;
        BunObj *b = right.as.obj;
        for (size_t index = 0; index < a->count; index++) {
            bun_list_push(result.as.obj, a->items[index]);
        }
        for (size_t index = 0; index < b->count; index++) {
            bun_list_push(result.as.obj, b->items[index]);
        }
        return result;
    }
    if (bun_is_number(left) && bun_is_number(right)) {
        if (left.tag == BUN_INT && right.tag == BUN_INT) {
            return bun_int_value(bun_add_int(left.as.i, right.as.i));
        }
        return bun_float_value(bun_as_double(left) + bun_as_double(right));
    }
    if (left.tag == BUN_STR || right.tag == BUN_STR) {
        return bun_str_concat(bun_str_from_c(bun_stringify(left)),
                              bun_str_from_c(bun_stringify(right)));
    }
    bun_throw("unsupported operands for '+'");
    return bun_null_value();
}

static BunValue bun_sub_slow(BunValue left, BunValue right);

static inline BunValue bun_sub(BunValue left, BunValue right) {
    if (left.tag == BUN_INT && right.tag == BUN_INT) {
        return bun_int_value(bun_sub_int(left.as.i, right.as.i));
    }
    return bun_sub_slow(left, right);
}

static BunValue bun_sub_slow(BunValue left, BunValue right) {
    if (left.tag == BUN_SET && right.tag == BUN_SET) {
        return bun_set_difference(left.as.obj, right.as.obj);
    }
    if (!bun_is_number(left) || !bun_is_number(right)) {
        bun_throw("unsupported operands for '-'");
    }
    if (left.tag == BUN_INT && right.tag == BUN_INT) {
        return bun_int_value(bun_sub_int(left.as.i, right.as.i));
    }
    return bun_float_value(bun_as_double(left) - bun_as_double(right));
}

static BunValue bun_mul_slow(BunValue left, BunValue right);

static inline BunValue bun_mul(BunValue left, BunValue right) {
    if (left.tag == BUN_INT && right.tag == BUN_INT) {
        return bun_int_value(bun_mul_int(left.as.i, right.as.i));
    }
    return bun_mul_slow(left, right);
}

static BunValue bun_mul_slow(BunValue left, BunValue right) {
    if (!bun_is_number(left) || !bun_is_number(right)) {
        bun_throw("unsupported operands for '*'");
    }
    if (left.tag == BUN_INT && right.tag == BUN_INT) {
        return bun_int_value(bun_mul_int(left.as.i, right.as.i));
    }
    return bun_float_value(bun_as_double(left) * bun_as_double(right));
}

static int64_t bun_floor_div(int64_t left, int64_t right) {
    int64_t quotient = left / right;
    if ((left % right != 0) && ((left < 0) != (right < 0))) {
        quotient -= 1;
    }
    return quotient;
}

static BunValue bun_div_slow(BunValue left, BunValue right);

static inline BunValue bun_div(BunValue left, BunValue right) {
    if (left.tag == BUN_INT && right.tag == BUN_INT) {
        if (right.as.i == 0) {
            bun_throw("division by zero");
        }
        if (left.as.i == BUN_INT_MIN && right.as.i == -1) {
            return bun_int_value(bun_int_overflow());
        }
        return bun_int_value(bun_floor_div(left.as.i, right.as.i));
    }
    return bun_div_slow(left, right);
}

static BunValue bun_div_slow(BunValue left, BunValue right) {
    if (!bun_is_number(left) || !bun_is_number(right)) {
        bun_throw("unsupported operands for '/'");
    }
    if (bun_as_double(right) == 0.0) {
        bun_throw("division by zero");
    }
    if (left.tag == BUN_INT && right.tag == BUN_INT) {
        if (left.as.i == BUN_INT_MIN && right.as.i == -1) {
            return bun_int_value(bun_int_overflow());
        }
        return bun_int_value(bun_floor_div(left.as.i, right.as.i));
    }
    return bun_float_value(bun_as_double(left) / bun_as_double(right));
}

static BunValue bun_mod_slow(BunValue left, BunValue right);

static inline BunValue bun_mod(BunValue left, BunValue right) {
    if (left.tag == BUN_INT && right.tag == BUN_INT) {
        if (right.as.i == 0) {
            bun_throw("division by zero");
        }
        return bun_int_value(bun_mod_int(left.as.i, right.as.i));
    }
    return bun_mod_slow(left, right);
}

static BunValue bun_mod_slow(BunValue left, BunValue right) {
    if (!bun_is_number(left) || !bun_is_number(right)) {
        bun_throw("unsupported operands for '%'");
    }
    if (bun_as_double(right) == 0.0) {
        bun_throw("division by zero");
    }
    if (left.tag == BUN_INT && right.tag == BUN_INT) {
        return bun_int_value(bun_mod_int(left.as.i, right.as.i));
    }
    double a = bun_as_double(left);
    double b = bun_as_double(right);
    double rest = fmod(a, b);
    if (rest != 0.0 && ((rest < 0.0) != (b < 0.0))) {
        rest += b;
    }
    return bun_float_value(rest);
}

static BunValue bun_pow(BunValue left, BunValue right) {
    if (!bun_is_number(left) || !bun_is_number(right)) {
        bun_throw("unsupported operands for '**'");
    }
    if (left.tag == BUN_INT && right.tag == BUN_INT) {
        int64_t base = left.as.i;
        int64_t exponent = right.as.i;
        if (exponent < 0) {
            return bun_float_value(pow((double)base, (double)exponent));
        }
        int64_t result = 1;
        for (int64_t step = 0; step < exponent; step++) {
            result = bun_mul_int(result, base);
        }
        return bun_int_value(result);
    }
    double base = bun_as_double(left);
    double exponent = bun_as_double(right);
    if (base < 0 && exponent != floor(exponent)) {
        bun_throw("cannot raise a negative number to a fractional power");
    }
    return bun_float_value(pow(base, exponent));
}

static BunValue bun_compare_slow(BunValue left, BunValue right, int op);

static inline BunValue bun_compare(BunValue left, BunValue right, int op) {
    if (left.tag == BUN_INT && right.tag == BUN_INT) {
        int64_t a = left.as.i;
        int64_t b = right.as.i;
        if (op == 0) {
            return bun_bool_value(a < b);
        }
        if (op == 1) {
            return bun_bool_value(a <= b);
        }
        if (op == 2) {
            return bun_bool_value(a > b);
        }
        return bun_bool_value(a >= b);
    }
    return bun_compare_slow(left, right, op);
}

static BunValue bun_compare_slow(BunValue left, BunValue right, int op) {    if ((bun_is_number(left) && bun_is_number(right)) ||
        (left.tag == BUN_STR && right.tag == BUN_STR)) {
        int result;
        if (left.tag == BUN_INT && right.tag == BUN_INT) {
            result = left.as.i < right.as.i ? -1 : (left.as.i > right.as.i ? 1 : 0);
        } else if (left.tag == BUN_STR) {
            int order = strcmp(left.as.obj->data, right.as.obj->data);
            result = order < 0 ? -1 : (order > 0 ? 1 : 0);
        } else {
            double a = bun_as_double(left);
            double b = bun_as_double(right);
            result = a < b ? -1 : (a > b ? 1 : 0);
        }
        switch (op) {
        case 0:
            return bun_bool_value(result < 0);
        case 1:
            return bun_bool_value(result <= 0);
        case 2:
            return bun_bool_value(result > 0);
        default:
            return bun_bool_value(result >= 0);
        }
    }
    bun_throw("unsupported operands for '%s'",
              op == 0 ? "<" : (op == 1 ? "<=" : (op == 2 ? ">" : ">=")));
    return bun_null_value();
}

static BunValue bun_bits(BunValue left, BunValue right, int op) {
    if (left.tag == BUN_SET && right.tag == BUN_SET) {
        if (op == 0) {
            return bun_set_intersection(left.as.obj, right.as.obj);
        }
        if (op == 1) {
            return bun_set_union(left.as.obj, right.as.obj);
        }
        if (op == 2) {
            BunValue first = bun_set_difference(left.as.obj, right.as.obj);
            BunValue second = bun_set_difference(right.as.obj, left.as.obj);
            return bun_set_union(first.as.obj, second.as.obj);
        }
    }
    if (left.tag != BUN_INT || right.tag != BUN_INT) {
        bun_throw("unsupported operands for '%s'",
                  op == 0 ? "&" : (op == 1 ? "|" : (op == 2 ? "^" :
                      (op == 3 ? "<<" : ">>"))));
    }
    int64_t a = left.as.i;
    int64_t b = right.as.i;
    switch (op) {
    case 0:
        return bun_int_value(a & b);
    case 1:
        return bun_int_value(a | b);
    case 2:
        return bun_int_value(a ^ b);
    default:
        if (b < 0) {
            bun_throw("negative shift count");
        }
        if (op == 3) {
            return bun_int_value(bun_shl_int(a, b));
        }
        return bun_int_value(bun_shr_int(a, b));
    }
}

static BunValue bun_negate_slow(BunValue value);

static inline BunValue bun_negate(BunValue value) {
    if (value.tag == BUN_INT) {
        if (value.as.i == BUN_INT_MIN) {
            return bun_int_value(bun_int_overflow());
        }
        return bun_int_value(-value.as.i);
    }
    return bun_negate_slow(value);
}

static BunValue bun_negate_slow(BunValue value) {
    if (!bun_is_number(value)) {
        bun_throw("unary '-' expects a number");
    }
    if (value.tag == BUN_INT) {
        if (value.as.i == BUN_INT_MIN) {
            return bun_int_value(bun_int_overflow());
        }
        return bun_int_value(-value.as.i);
    }
    return bun_float_value(-value.as.f);
}

static BunValue bun_invert(BunValue value) {
    if (value.tag != BUN_INT) {
        bun_throw("unary '~' expects an integer");
    }
    if (value.as.i == BUN_INT_MIN) {
        return bun_int_value(bun_int_overflow());
    }
    return bun_int_value(~value.as.i);
}

/* ------------------------------------------------------------------ */
/* The indexing and the slicing                                        */
/* ------------------------------------------------------------------ */

static BunValue bun_index(BunValue object, BunValue index) {
    if (object.tag == BUN_LIST) {
        if (index.tag != BUN_INT) {
            bun_throw("index must be an integer");
        }
        BunObj *list = object.as.obj;
        if (index.as.i < 0 || (size_t)index.as.i >= list->count) {
            bun_throw("index %lld out of range", (long long)index.as.i);
        }
        return list->items[index.as.i];
    }
    if (object.tag == BUN_STR) {
        if (index.tag != BUN_INT) {
            bun_throw("index must be an integer");
        }
        BunObj *text = object.as.obj;
        if (index.as.i < 0 || (size_t)index.as.i >= text->len) {
            bun_throw("index %lld out of range", (long long)index.as.i);
        }
        return bun_str_new(text->data + index.as.i, 1);
    }
    if (object.tag == BUN_DICT) {
        return bun_dict_get(object.as.obj, index);
    }
    bun_throw("value is not indexable");
    return bun_null_value();
}

static void bun_store_index(BunValue object, BunValue index, BunValue value) {
    if (object.tag == BUN_DICT) {
        bun_dict_set(object.as.obj, index, value);
        return;
    }
    if (object.tag != BUN_LIST) {
        bun_throw("can only assign into a list");
    }
    if (index.tag != BUN_INT) {
        bun_throw("list index must be an integer");
    }
    BunObj *list = object.as.obj;
    if (index.as.i < 0 || (size_t)index.as.i >= list->count) {
        bun_throw("list index %lld out of range", (long long)index.as.i);
    }
    list->items[index.as.i] = value;
}

static void bun_check_slice_bounds(BunValue start, BunValue stop,
                                    BunValue step) {
    const char *names[3] = { "start", "stop", "step" };
    BunValue bounds[3] = { start, stop, step };
    for (int index = 0; index < 3; index++) {
        if (bounds[index].tag == BUN_NULL) {
            continue;
        }
        if (bounds[index].tag != BUN_INT) {
            bun_throw("slice %s must be an integer", names[index]);
        }
    }
    if (step.tag != BUN_NULL && step.as.i == 0) {
        bun_throw("slice step cannot be zero");
    }
}

/* The bounds of a slice, the way Python resolves them. */
static void bun_slice_indices(size_t length, BunValue start, BunValue stop,
                              BunValue step, int64_t *first, int64_t *last,
                              int64_t *stride) {
    int64_t step_value = 1;
    if (step.tag != BUN_NULL) {
        step_value = step.as.i;
    }
    int64_t lower = 0;
    int64_t upper = (int64_t)length;
    if (step_value < 0) {
        lower = -1;
        upper = (int64_t)length - 1;
    }
    int64_t start_value;
    if (start.tag == BUN_NULL) {
        start_value = step_value < 0 ? upper : lower;
    } else {
        start_value = start.as.i;
        if (start_value < 0) {
            start_value += (int64_t)length;
            if (start_value < lower) {
                start_value = lower;
            }
            if (start_value > upper) {
                start_value = upper;
            }
        } else if (start_value > upper) {
            start_value = upper;
        }
    }
    int64_t stop_value;
    if (stop.tag == BUN_NULL) {
        stop_value = step_value < 0 ? lower : upper;
    } else {
        stop_value = stop.as.i;
        if (stop_value < 0) {
            stop_value += (int64_t)length;
            if (stop_value < lower) {
                stop_value = lower;
            }
            if (stop_value > upper) {
                stop_value = upper;
            }
        } else if (stop_value > upper) {
            stop_value = upper;
        }
    }
    *first = start_value;
    *last = stop_value;
    *stride = step_value;
}

static BunValue bun_slice(BunValue object, BunValue start, BunValue stop,
                           BunValue step) {
    if (object.tag != BUN_LIST && object.tag != BUN_STR) {
        bun_throw("value is not sliceable");
    }
    bun_check_slice_bounds(start, stop, step);
    size_t length = object.as.obj->len;
    if (object.tag == BUN_LIST) {
        length = object.as.obj->count;
    }
    int64_t first, last, stride;
    bun_slice_indices(length, start, stop, step, &first, &last, &stride);
    BunValue result = object.tag == BUN_STR ? bun_str_new("", 0) : bun_list_new();
    if (stride > 0) {
        for (int64_t at = first; at < last; at += stride) {
            if (object.tag == BUN_STR) {
                result = bun_str_concat(
                    result, bun_str_new(object.as.obj->data + at, 1));
            } else {
                bun_list_push(result.as.obj, object.as.obj->items[at]);
            }
        }
    } else {
        for (int64_t at = first; at > last; at += stride) {
            if (object.tag == BUN_STR) {
                result = bun_str_concat(
                    result, bun_str_new(object.as.obj->data + at, 1));
            } else {
                bun_list_push(result.as.obj, object.as.obj->items[at]);
            }
        }
    }
    return result;
}

static void bun_store_slice(BunValue object, BunValue start, BunValue stop,
                             BunValue step, BunValue value) {
    if (object.tag != BUN_LIST) {
        bun_throw("value is not sliceable");
    }
    if (value.tag != BUN_LIST) {
        bun_throw("can only assign a list to a slice");
    }
    bun_check_slice_bounds(start, stop, step);
    BunObj *list = object.as.obj;
    int64_t first, last, stride;
    bun_slice_indices(list->count, start, stop, step, &first, &last, &stride);
    BunObj *items = value.as.obj;
    if (stride == 1) {
        /* A simple slice: the list takes the new values, and its length
         * follows the length of the new values. */
        int64_t count = last - first;
        if (count < 0) {
            count = 0;
        }
        size_t tail = list->count - (size_t)(first + count);
        size_t new_count = list->count - (size_t)count + items->count;
        while (list->cap < new_count) {
            list->cap = list->cap * 2;
            BunValue *grown =
                (BunValue *)bun_alloc(sizeof(BunValue) * list->cap);
            memcpy(grown, list->items, sizeof(BunValue) * list->count);
            list->items = grown;
        }
        if (tail > 0) {
            memmove(list->items + first + items->count,
                    list->items + first + count,
                    tail * sizeof(BunValue));
        }
        for (size_t index = 0; index < items->count; index++) {
            list->items[first + index] = items->items[index];
        }
        list->count = new_count;
        return;
    }
    int64_t count = 0;
    if (stride > 0) {
        for (int64_t at = first; at < last; at += stride) {
            count++;
        }
    } else {
        for (int64_t at = first; at > last; at += stride) {
            count++;
        }
    }
    if ((size_t)count != items->count) {
        bun_throw(
            "attempt to assign sequence of size %zu to extended slice of "
            "size %lld", items->count, (long long)count);
    }
    int64_t index = 0;
    if (stride > 0) {
        for (int64_t at = first; at < last; at += stride) {
            list->items[at] = items->items[index++];
        }
    } else {
        for (int64_t at = first; at > last; at += stride) {
            list->items[at] = items->items[index++];
        }
    }
}

/* ------------------------------------------------------------------ */
/* The patterns                                                        */
/* ------------------------------------------------------------------ */

/* A pattern of a match statement, as the emitter writes it.  The emitter
 * turns the plan of a pattern into this shape, and the runtime tests a
 * value against it. */
typedef struct BunPlan {
    int kind;
    BunValue literal;          /* the value of a literal, the name of a type */
    const char *name;          /* the name of a binding */
    BunValue low;              /* the low bound of a range */
    BunValue high;             /* the high bound of a range */
    const struct BunPlan *const *items;   /* the items of a list or of an or */
    int count;
    const char *const *keys;    /* the keys of a dictionary */
    const struct BunPlan *const *values;  /* the plans of the values */
    const struct BunPlan *tail; /* the tail of a list */
} BunPlan;

#define BUN_PLAN_LITERAL 1
#define BUN_PLAN_WILDCARD 2
#define BUN_PLAN_BINDING 3
#define BUN_PLAN_TYPE 4
#define BUN_PLAN_RANGE 5
#define BUN_PLAN_LIST 6
#define BUN_PLAN_DICT 7
#define BUN_PLAN_OR 8
#define BUN_PLAN_STRUCT 9

/* The names a pattern binds.  They are collected first and applied after,
 * so a pattern that fails halfway leaves nothing behind. */
typedef struct BunMatchList {
    BunBinding *items;
    int count;
    int cap;
} BunMatchList;

static void bun_match_push(BunMatchList *list, const char *name,
                            BunValue value) {
    if (list->count >= list->cap) {
        int cap = list->cap == 0 ? 8 : list->cap * 2;
        BunBinding *items =
            (BunBinding *)bun_alloc(sizeof(BunBinding) * (size_t)cap);
        if (list->count > 0) {
            memcpy(items, list->items,
                   sizeof(BunBinding) * (size_t)list->count);
        }
        list->items = items;
        list->cap = cap;
    }
    list->items[list->count].name = name;
    list->items[list->count].value = value;
    list->items[list->count].mutable = 1;
    list->count++;
}

/* The name of the type of a value, as the type patterns use it. */
static const char *bun_pattern_type_name(BunValue value) {
    if (value.tag == BUN_FUNC || value.tag == BUN_BUILTIN) {
        return "fn";
    }
    return bun_type_name(value);
}

/* Whether a number is smaller than another one. */
static int bun_number_less(BunValue left, BunValue right) {
    if (left.tag == BUN_INT && right.tag == BUN_INT) {
        return left.as.i < right.as.i;
    }
    return bun_as_double(left) < bun_as_double(right);
}

static int bun_match_plan(BunValue value, const BunPlan *plan,
                           BunMatchList *out);

static int bun_match_list(BunValue value, const BunPlan *plan,
                           BunMatchList *out) {
    BunObj *list = value.as.obj;
    int index;
    if (plan->tail == NULL) {
        if (list->count != (size_t)plan->count) {
            return 0;
        }
    } else if (list->count < (size_t)plan->count) {
        return 0;
    }
    for (index = 0; index < plan->count; index++) {
        if (!bun_match_plan(list->items[index], plan->items[index], out)) {
            return 0;
        }
    }
    if (plan->tail != NULL) {
        /* The tail takes the rest of the list. */
        BunValue rest = bun_list_new();
        for (size_t item = (size_t)plan->count; item < list->count; item++) {
            bun_list_push(rest.as.obj, list->items[item]);
        }
        return bun_match_plan(rest, plan->tail, out);
    }
    return 1;
}

static int bun_match_plan(BunValue value, const BunPlan *plan,
                           BunMatchList *out) {
    switch (plan->kind) {
    case BUN_PLAN_LITERAL:
        return bun_values_equal(value, plan->literal);
    case BUN_PLAN_WILDCARD:
        return 1;
    case BUN_PLAN_BINDING:
        bun_match_push(out, plan->name, value);
        return 1;
    case BUN_PLAN_TYPE:
        if (plan->literal.tag != BUN_STR) {
            return 0;
        }
        return strcmp(bun_pattern_type_name(value),
                      plan->literal.as.obj->data) == 0;
    case BUN_PLAN_RANGE: {
        int after_low;
        int before_high;
        if (!bun_is_number(value) || !bun_is_number(plan->low)
                || !bun_is_number(plan->high)) {
            return 0;
        }
        after_low = bun_number_less(plan->low, value)
            || bun_values_equal(plan->low, value);
        before_high = bun_number_less(value, plan->high)
            || bun_values_equal(value, plan->high);
        return after_low && before_high;
    }
    case BUN_PLAN_LIST:
        if (value.tag != BUN_LIST) {
            return 0;
        }
        return bun_match_list(value, plan, out);
    case BUN_PLAN_DICT:
        if (value.tag != BUN_DICT) {
            return 0;
        }
        for (int index = 0; index < plan->count; index++) {
            BunValue key = bun_str_from_c(plan->keys[index]);
            BunObj *dict = value.as.obj;
            if (!bun_dict_has(dict, key)) {
                return 0;
            }
            if (!bun_match_plan(bun_dict_get(dict, key), plan->values[index],
                                out)) {
                return 0;
            }
        }
        return 1;
    case BUN_PLAN_OR: {
        for (int index = 0; index < plan->count; index++) {
            BunMatchList found = { NULL, 0, 0 };
            if (bun_match_plan(value, plan->items[index], &found)) {
                for (int item = 0; item < found.count; item++) {
                    bun_match_push(out, found.items[item].name,
                                   found.items[item].value);
                }
                return 1;
            }
        }
        return 0;
    }
    case BUN_PLAN_STRUCT: {
        /* A struct of the named type, with its fields matched the way
         * the entries of a dict are matched. */
        if (value.tag != BUN_STRUCT) {
            return 0;
        }
        if (plan->literal.tag != BUN_STR) {
            return 0;
        }
        BunObj *object = value.as.obj;
        if (strcmp(object->name, plan->literal.as.obj->data) != 0) {
            return 0;
        }
        for (int index = 0; index < plan->count; index++) {
            int at = bun_struct_field(object, plan->keys[index]);
            if (at < 0) {
                return 0;
            }
            if (!bun_match_plan(object->field_values[at],
                                plan->values[index], out)) {
                return 0;
            }
        }
        return 1;
    }
    }
    return 0;
}

/* ------------------------------------------------------------------ */
/* The unpacking                                                       */
/* ------------------------------------------------------------------ */

/* The plan of an unpacking is a text: one letter per target, `l` for a
 * target and `s` for a star.  The values fill the registers from the
 * last one to the first one, the way the register machine does. */
static void bun_unpack(BunValue value, const char *plan, BunValue *out) {
    size_t count = strlen(plan);
    if (value.tag == BUN_STR) {
        BunObj *text = value.as.obj;
        BunValue items[256];
        size_t total = text->len;
        if (total > 256) {
            bun_throw("cannot unpack a string of %zu characters", total);
        }
        for (size_t index = 0; index < total; index++) {
            items[index] = bun_str_new(text->data + index, 1);
        }
        size_t required = 0;
        for (size_t index = 0; index < count; index++) {
            if (plan[index] != 's') {
                required++;
            }
        }
        if (total < required) {
            bun_throw("not enough values to unpack (expected %zu, got %zu)",
                      required, total);
        }
        if (total > required && strchr(plan, 's') == NULL) {
            bun_throw("too many values to unpack (expected %zu)", required);
        }
        size_t star_at = count;
        size_t trailing = 0;
        for (size_t index = 0; index < count; index++) {
            if (plan[index] == 's') {
                star_at = index;
                break;
            }
        }
        for (size_t index = star_at + 1; index < count; index++) {
            if (plan[index] != 's') {
                trailing++;
            }
        }
        size_t at = 0;
        for (size_t index = 0; index < count; index++) {
            if (plan[index] == 's') {
                size_t end = total - trailing;
                BunValue list = bun_list_new();
                for (size_t item = at; item < end; item++) {
                    bun_list_push(list.as.obj, items[item]);
                }
                at = end;
                out[count - index - 1] = list;
            } else {
                out[count - index - 1] = items[at++];
            }
        }
        return;
    }
    if (value.tag != BUN_LIST) {
        bun_throw("cannot unpack %s",
                  value.tag == BUN_NULL ? "null" :
                  (value.tag == BUN_BOOL ? "boolean" :
                   (bun_is_number(value) ? "number" :
                    (value.tag == BUN_STR ? "string" : "value"))));
    }
    BunObj *list = value.as.obj;
    size_t required = 0;
    for (size_t index = 0; index < count; index++) {
        if (plan[index] != 's') {
            required++;
        }
    }
    if (list->count < required) {
        bun_throw("not enough values to unpack (expected %zu, got %zu)",
                  required, list->count);
    }
    size_t star_at = count;
    size_t trailing = 0;
    for (size_t index = 0; index < count; index++) {
        if (plan[index] == 's') {
            star_at = index;
            break;
        }
    }
    if (star_at == count && list->count > required) {
        bun_throw("too many values to unpack (expected %zu)", required);
    }
    for (size_t index = star_at + 1; index < count; index++) {
        if (plan[index] != 's') {
            trailing++;
        }
    }
    size_t at = 0;
    for (size_t index = 0; index < count; index++) {
        if (plan[index] == 's') {
            size_t end = list->count - trailing;
            BunValue items = bun_list_new();
            for (size_t item = at; item < end; item++) {
                bun_list_push(items.as.obj, list->items[item]);
            }
            at = end;
            out[count - index - 1] = items;
        } else {
            out[count - index - 1] = list->items[at++];
        }
    }
}

/* ------------------------------------------------------------------ */
/* The format of a value                                               */
/* ------------------------------------------------------------------ */

static char *bun_group_digits(const char *text) {
    int negative = text[0] == '-';
    const char *start = negative ? text + 1 : text;
    size_t len = strlen(start);
    size_t groups = (len + 2) / 3;
    size_t size = len + groups + 2;
    char *out = (char *)bun_alloc(size);
    size_t at = 0;
    if (negative) {
        out[at++] = '-';
    }
    size_t first = len % 3;
    if (first == 0) {
        first = 3;
    }
    size_t index = 0;
    while (index < first) {
        out[at++] = start[index++];
    }
    while (index < len) {
        out[at++] = ',';
        out[at++] = start[index++];
        out[at++] = start[index++];
        out[at++] = start[index++];
    }
    out[at] = '\0';
    return out;
}

static char *bun_pad(const char *text, char fill, char align, int width) {
    size_t len = strlen(text);
    if ((int)len >= width) {
        return (char *)text;
    }
    int padding = width - (int)len;
    char *out = (char *)bun_alloc((size_t)width + 1);
    size_t at = 0;
    if (align == '<') {
        memcpy(out, text, len);
        at = len;
        while ((int)at < width) {
            out[at++] = fill;
        }
    } else if (align == '^') {
        int left = padding / 2;
        for (int index = 0; index < left; index++) {
            out[at++] = fill;
        }
        memcpy(out + at, text, len);
        at += len;
        while ((int)at < width) {
            out[at++] = fill;
        }
    } else {
        for (int index = 0; index < padding; index++) {
            out[at++] = fill;
        }
        memcpy(out + at, text, len);
        at += len;
    }
    out[at] = '\0';
    return out;
}

/* The value of a format specification, the way the runtime formats it. */
static char *bun_format_value(BunValue value, const char *spec) {
    if (spec == NULL || spec[0] == '\0') {
        return bun_stringify(value);
    }
    char fill = ' ';
    char align = 0;
    size_t index = 0;
    if (strlen(spec) >= 2 && strchr("<>=^", spec[1])) {
        fill = spec[0];
        align = spec[1];
        index = 2;
    } else if (strchr("<>=^", spec[0])) {
        align = spec[0];
        index = 1;
    }
    char sign = 0;
    if (index < strlen(spec) && strchr("+- ", spec[index])) {
        sign = spec[index];
        index++;
    }
    if (index < strlen(spec) && spec[index] == '#') {
        index++;
    }
    int zero = 0;
    if (index < strlen(spec) && spec[index] == '0') {
        zero = 1;
        index++;
    }
    int width = 0;
    while (index < strlen(spec) && isdigit((unsigned char)spec[index])) {
        width = width * 10 + (spec[index] - '0');
        index++;
    }
    int grouping = 0;
    if (index < strlen(spec) && spec[index] == ',') {
        grouping = 1;
        index++;
    }
    int precision = -1;
    if (index < strlen(spec) && spec[index] == '.') {
        index++;
        precision = 0;
        while (index < strlen(spec) && isdigit((unsigned char)spec[index])) {
            precision = precision * 10 + (spec[index] - '0');
            index++;
        }
    }
    char kind = 0;
    if (index < strlen(spec)) {
        kind = spec[index];
        index++;
    }
    if (index != strlen(spec)) {
        bun_throw("invalid format spec '%s'", spec);
    }
    char buffer[512];
    int negative = 0;
    if (value.tag == BUN_BOOL) {
        snprintf(buffer, sizeof(buffer), "%s", value.as.b ? "true" : "false");
    } else if (value.tag == BUN_INT) {
        negative = value.as.i < 0;
        int64_t number = negative ? -value.as.i : value.as.i;
        if (kind == 0 || kind == 'd') {
            snprintf(buffer, sizeof(buffer), "%lld", (long long)number);
        } else if (kind == 'x') {
            snprintf(buffer, sizeof(buffer), "%llx", (long long)number);
        } else if (kind == 'X') {
            snprintf(buffer, sizeof(buffer), "%llX", (long long)number);
        } else if (kind == 'o') {
            snprintf(buffer, sizeof(buffer), "%llo", (long long)number);
        } else if (kind == 'b') {
            char bits[80];
            int at = 0;
            if (number == 0) {
                bits[at++] = '0';
            }
            while (number > 0 && at < 78) {
                bits[at++] = (char)('0' + (number & 1));
                number >>= 1;
            }
            for (int position = 0; position < at; position++) {
                buffer[position] = bits[at - position - 1];
            }
            buffer[at] = '\0';
        } else if (kind == 'c') {
            snprintf(buffer, sizeof(buffer), "%c", (int)number);
        } else if (kind == 'f' || kind == 'e' || kind == 'g' || kind == 'E' ||
                   kind == 'G') {
            snprintf(buffer, sizeof(buffer), "%.*%c",
                     precision < 0 ? 6 : precision, kind, (double)value.as.i);
        } else {
            snprintf(buffer, sizeof(buffer), "%lld", (long long)number);
        }
    } else if (value.tag == BUN_FLOAT) {
        negative = value.as.f < 0;
        if (kind == 0 || kind == 'd') {
            char *text = (char *)bun_alloc(64);
            bun_format_float(text, 64, value.as.f);
            snprintf(buffer, sizeof(buffer), "%s", text);
        } else if (kind == 'f' || kind == 'F') {
            snprintf(buffer, sizeof(buffer), "%.*f",
                     precision < 0 ? 6 : precision, value.as.f);
        } else if (kind == 'e' || kind == 'E') {
            snprintf(buffer, sizeof(buffer), "%.*%c",
                     precision < 0 ? 6 : precision, kind, value.as.f);
        } else if (kind == 'g' || kind == 'G') {
            snprintf(buffer, sizeof(buffer), "%.*%c",
                     precision < 0 ? 6 : precision, kind, value.as.f);
        } else if (kind == '%') {
            snprintf(buffer, sizeof(buffer), "%.*f%%",
                     precision < 0 ? 6 : precision, value.as.f * 100.0);
        } else {
            char *text = (char *)bun_alloc(64);
            bun_format_float(text, 64, value.as.f);
            snprintf(buffer, sizeof(buffer), "%s", text);
        }
    } else if (value.tag == BUN_STR) {
        snprintf(buffer, sizeof(buffer), "%s", value.as.obj->data);
        if (precision >= 0 && (int)strlen(buffer) > precision) {
            buffer[precision] = '\0';
        }
    } else {
        snprintf(buffer, sizeof(buffer), "%s", bun_stringify(value));
    }
    char *text = buffer;
    if (negative) {
        char signed_text[600];
        snprintf(signed_text, sizeof(signed_text), "-%s", buffer);
        text = signed_text;
    } else if (sign == '+') {
        char signed_text[600];
        snprintf(signed_text, sizeof(signed_text), "+%s", buffer);
        text = signed_text;
    } else if (sign == ' ') {
        char signed_text[600];
        snprintf(signed_text, sizeof(signed_text), " %s", buffer);
        text = signed_text;
    }
    if (grouping) {
        text = bun_group_digits(text);
    }
    if (!align) {
        if (zero) {
            align = '=';
        } else if (kind && kind != 's' && kind != 'c') {
            align = '>';
        } else {
            align = '<';
        }
    }
    if (align == '=') {
        int sign_len = (text[0] == '-' || text[0] == '+' || text[0] == ' ') ? 1 : 0;
        int len = (int)strlen(text);
        if (len < width) {
            char *out = (char *)bun_alloc((size_t)width + 1);
            memcpy(out, text, (size_t)sign_len);
            for (int index = sign_len; index < width; index++) {
                out[index] = '0';
            }
            memcpy(out + width - (len - sign_len), text + sign_len,
                   (size_t)(len - sign_len));
            out[width] = '\0';
            return out;
        }
        return text;
    }
    return bun_pad(text, fill, align, width);
}

static BunValue bun_format(BunValue value, const char *spec, const char *conv,
                            const char *source_text) {
    if (source_text != NULL) {
        char *part = bun_format_value(value, spec);
        size_t size = strlen(source_text) + strlen(part) + 1;
        char *out = (char *)bun_alloc(size);
        snprintf(out, size, "%s%s", source_text, part);
        return bun_str_from_c(out);
    }
    if (conv != NULL && strcmp(conv, "r") == 0) {
        return bun_str_from_c(bun_repr(value));
    }
    if (conv != NULL && strcmp(conv, "s") == 0) {
        return bun_str_from_c(bun_stringify(value));
    }
    return bun_str_from_c(bun_format_value(value, spec));
}

/* ------------------------------------------------------------------ */
/* The functions and the builtins                                      */
/* ------------------------------------------------------------------ */

static BunValue bun_call(BunValue callee, BunValue *args, int count,
                          BunValue kwargs);

static BunValue bun_make_function(const char *name, BunFn fn, BunEnv *closure,
                                  const BunParam *params, int param_count,
                                  int needs_env) {
    BunObj *object = bun_new_obj(BUN_FUNC);
    object->name = name;
    object->fn = fn;
    object->closure = closure;
    object->params = params;
    object->param_count = param_count;
    object->needs_env = needs_env;
    return bun_obj_value(object);
}

static BunValue bun_make_builtin(const char *name, BunBuiltinFn fn) {
    BunObj *object = bun_new_obj(BUN_BUILTIN);
    object->name = name;
    object->builtin = fn;
    return bun_obj_value(object);
}

static BunValue bun_builtin_print(BunValue *args, int count) {
    size_t size = 1;
    for (int index = 0; index < count; index++) {
        size += strlen(bun_stringify(args[index])) + 1;
    }
    char *out = (char *)bun_alloc(size);
    size_t at = 0;
    for (int index = 0; index < count; index++) {
        if (index) {
            out[at++] = ' ';
        }
        const char *text = bun_stringify(args[index]);
        size_t len = strlen(text);
        memcpy(out + at, text, len);
        at += len;
    }
    out[at] = '\0';
    printf("%s\n", out);
    return bun_null_value();
}

static BunValue bun_builtin_len(BunValue *args, int count) {
    if (count != 1) {
        bun_throw("len() expects 1 argument");
    }
    if (args[0].tag == BUN_STR) {
        return bun_int_value((int64_t)args[0].as.obj->len);
    }
    if (args[0].tag == BUN_LIST) {
        return bun_int_value((int64_t)args[0].as.obj->count);
    }
    bun_throw("len() expects a string or list");
    return bun_null_value();
}

static BunValue bun_builtin_str(BunValue *args, int count) {
    if (count != 1) {
        bun_throw("str() expects 1 argument");
    }
    return bun_str_from_c(bun_stringify(args[0]));
}

static BunValue bun_builtin_bool(BunValue *args, int count) {
    if (count != 1) {
        bun_throw("bool() expects 1 argument");
    }
    return bun_bool_value(bun_truthy(args[0]));
}

static BunValue bun_builtin_type_of(BunValue *args, int count) {
    if (count != 1) {
        bun_throw("type_of() expects 1 argument");
    }
    return bun_str_from_c(bun_public_type_name(args[0]));
}

static BunValue bun_builtin_float(BunValue *args, int count) {
    if (count != 1) {
        bun_throw("float() expects 1 argument");
    }
    BunValue value = args[0];
    if (value.tag == BUN_BOOL) {
        return bun_float_value(value.as.b ? 1.0 : 0.0);
    }
    if (value.tag == BUN_INT) {
        return bun_float_value((double)value.as.i);
    }
    if (value.tag == BUN_FLOAT) {
        return value;
    }
    if (value.tag == BUN_STR) {
        char *end = NULL;
        double number = strtod(value.as.obj->data, &end);
        if (!end || *end != '\0' || end == value.as.obj->data) {
            bun_throw("cannot convert '%s' to float", value.as.obj->data);
        }
        return bun_float_value(number);
    }
    bun_throw("cannot convert value to float");
    return bun_null_value();
}

static BunValue bun_builtin_int(BunValue *args, int count) {
    if (count != 1 && count != 2) {
        bun_throw("int() expects 1 or 2 arguments");
    }
    BunValue value = args[0];
    int base = 10;
    if (count == 2) {
        if (args[1].tag != BUN_INT) {
            bun_throw("int() expects base as int");
        }
        base = (int)args[1].as.i;
        if (base < 2 || base > 36) {
            bun_throw("int() base must be between 2 and 36");
        }
    }
    if (value.tag == BUN_BOOL) {
        return bun_int_value(value.as.b ? 1 : 0);
    }
    if (value.tag == BUN_INT) {
        return value;
    }
    if (value.tag == BUN_FLOAT) {
        double number = value.as.f;
        if (!(number >= -9223372036854775808.0 && number < 9223372036854775808.0)) {
            bun_throw("integer out of range");
        }
        return bun_int_value((int64_t)number);
    }
    if (value.tag == BUN_STR) {
        const char *text = value.as.obj->data;
        while (isspace((unsigned char)*text)) {
            text++;
        }
        char *end = NULL;
        errno = 0;
        long long number = strtoll(text, &end, base);
        if (!end || end == text) {
            bun_throw("cannot convert '%s' to int", value.as.obj->data);
        }
        while (isspace((unsigned char)*end)) {
            end++;
        }
        if (*end != '\0') {
            bun_throw("cannot convert '%s' to int", value.as.obj->data);
        }
        if (errno == ERANGE) {
            bun_throw("integer out of range");
        }
        return bun_int_value((int64_t)number);
    }
    bun_throw("cannot convert value to int");
    return bun_null_value();
}

static BunValue bun_builtin_abs(BunValue *args, int count) {
    if (count != 1) {
        bun_throw("abs() expects 1 argument");
    }
    if (args[0].tag == BUN_INT) {
        int64_t number = args[0].as.i;
        return bun_int_value(number < 0 ? -number : number);
    }
    if (args[0].tag == BUN_FLOAT) {
        return bun_float_value(fabs(args[0].as.f));
    }
    bun_throw("abs() expects a number");
    return bun_null_value();
}

/* The comparison of the sorting builtins.  The message is the one of
   the machine, so a program that sorts two dictionaries fails the same
   way under both engines. */
static int bun_sort_less(BunValue left, BunValue right) {
    if (left.tag == BUN_BOOL || right.tag == BUN_BOOL) {
        bun_throw("cannot compare a bool with a number");
    }
    if (bun_is_number(left) && bun_is_number(right)) {
        if (left.tag == BUN_INT && right.tag == BUN_INT) {
            return left.as.i < right.as.i;
        }
        return bun_as_double(left) < bun_as_double(right);
    }
    if (left.tag == BUN_STR && right.tag == BUN_STR) {
        return strcmp(left.as.obj->data, right.as.obj->data) < 0;
    }
    bun_throw("cannot compare a %s with a %s", bun_type_name(left),
              bun_type_name(right));
    return 0;
}

/* The merge sort of the `sorted` builtin.  The sort is a merge, so the
   order of two values that compare equal is the order they had: the
   sort of a list is stable. */
static void bun_merge_sort(BunValue *values, BunValue *scratch, int count) {
    if (count < 2) {
        return;
    }
    int middle = count / 2;
    bun_merge_sort(values, scratch, middle);
    bun_merge_sort(values + middle, scratch, count - middle);
    int left = 0;
    int right = middle;
    int at = 0;
    while (left < middle && right < count) {
        if (bun_sort_less(values[right], values[left])) {
            scratch[at++] = values[right++];
        } else {
            scratch[at++] = values[left++];
        }
    }
    while (left < middle) {
        scratch[at++] = values[left++];
    }
    while (right < count) {
        scratch[at++] = values[right++];
    }
    for (int index = 0; index < count; index++) {
        values[index] = scratch[index];
    }
}

static BunValue bun_builtin_min(BunValue *args, int count) {
    if (count != 1) {
        bun_throw("min() expects 1 argument");
    }
    if (args[0].tag != BUN_LIST) {
        bun_throw("min() expects a list");
    }
    BunObj *list = args[0].as.obj;
    if (list->count < 1) {
        bun_throw("min() expects a list with at least one value");
    }
    BunValue best = list->items[0];
    for (int index = 1; index < list->count; index++) {
        if (bun_sort_less(list->items[index], best)) {
            best = list->items[index];
        }
    }
    return best;
}

static BunValue bun_builtin_max(BunValue *args, int count) {
    if (count != 1) {
        bun_throw("max() expects 1 argument");
    }
    if (args[0].tag != BUN_LIST) {
        bun_throw("max() expects a list");
    }
    BunObj *list = args[0].as.obj;
    if (list->count < 1) {
        bun_throw("max() expects a list with at least one value");
    }
    BunValue best = list->items[0];
    for (int index = 1; index < list->count; index++) {
        if (bun_sort_less(best, list->items[index])) {
            best = list->items[index];
        }
    }
    return best;
}

static BunValue bun_builtin_sum(BunValue *args, int count) {
    if (count != 1) {
        bun_throw("sum() expects 1 argument");
    }
    if (args[0].tag != BUN_LIST) {
        bun_throw("sum() expects a list");
    }
    BunObj *list = args[0].as.obj;
    BunValue total = bun_int_value(0);
    for (int index = 0; index < list->count; index++) {
        BunValue item = list->items[index];
        if (item.tag == BUN_BOOL || !bun_is_number(item)) {
            bun_throw("sum() expects a list of numbers");
        }
        total = bun_add(total, item);
    }
    return total;
}

static BunValue bun_builtin_any(BunValue *args, int count) {
    if (count != 1) {
        bun_throw("any() expects 1 argument");
    }
    if (args[0].tag != BUN_LIST) {
        bun_throw("any() expects a list");
    }
    BunObj *list = args[0].as.obj;
    for (int index = 0; index < list->count; index++) {
        if (bun_truthy(list->items[index])) {
            return bun_bool_value(1);
        }
    }
    return bun_bool_value(0);
}

static BunValue bun_builtin_all(BunValue *args, int count) {
    if (count != 1) {
        bun_throw("all() expects 1 argument");
    }
    if (args[0].tag != BUN_LIST) {
        bun_throw("all() expects a list");
    }
    BunObj *list = args[0].as.obj;
    for (int index = 0; index < list->count; index++) {
        if (!bun_truthy(list->items[index])) {
            return bun_bool_value(0);
        }
    }
    return bun_bool_value(1);
}

static BunValue bun_builtin_zip(BunValue *args, int count) {
    if (count != 2) {
        bun_throw("zip() expects 2 arguments");
    }
    if (args[0].tag != BUN_LIST || args[1].tag != BUN_LIST) {
        bun_throw("zip() expects two lists");
    }
    BunObj *left = args[0].as.obj;
    BunObj *right = args[1].as.obj;
    int pairs = left->count < right->count ? left->count : right->count;
    BunValue result = bun_list_new();
    for (int index = 0; index < pairs; index++) {
        BunValue pair = bun_list_new();
        bun_list_push(pair.as.obj, left->items[index]);
        bun_list_push(pair.as.obj, right->items[index]);
        bun_list_push(result.as.obj, pair);
    }
    return result;
}

static BunValue bun_builtin_enumerate(BunValue *args, int count) {
    if (count != 1) {
        bun_throw("enumerate() expects 1 argument");
    }
    if (args[0].tag != BUN_LIST) {
        bun_throw("enumerate() expects a list");
    }
    BunObj *list = args[0].as.obj;
    BunValue result = bun_list_new();
    for (int index = 0; index < list->count; index++) {
        BunValue pair = bun_list_new();
        bun_list_push(pair.as.obj, bun_int_value(index));
        bun_list_push(pair.as.obj, list->items[index]);
        bun_list_push(result.as.obj, pair);
    }
    return result;
}

static BunValue bun_builtin_sorted(BunValue *args, int count) {
    if (count != 1) {
        bun_throw("sorted() expects 1 argument");
    }
    if (args[0].tag != BUN_LIST) {
        bun_throw("sorted() expects a list");
    }
    BunObj *list = args[0].as.obj;
    int size = list->count;
    BunValue result = bun_list_new();
    for (int index = 0; index < size; index++) {
        bun_list_push(result.as.obj, list->items[index]);
    }
    if (size > 1) {
        BunValue *scratch = (BunValue *)bun_alloc(sizeof(BunValue) * (size_t)size);
        bun_merge_sort(result.as.obj->items, scratch, size);
    }
    return result;
}

static BunValue bun_builtin_reversed(BunValue *args, int count) {
    if (count != 1) {
        bun_throw("reversed() expects 1 argument");
    }
    if (args[0].tag != BUN_LIST) {
        bun_throw("reversed() expects a list");
    }
    BunObj *list = args[0].as.obj;
    BunValue result = bun_list_new();
    for (int index = list->count - 1; index >= 0; index--) {
        bun_list_push(result.as.obj, list->items[index]);
    }
    return result;
}

static BunValue bun_builtin_range(BunValue *args, int count) {
    if (count < 1 || count > 3) {
        bun_throw("range() expects 1, 2 or 3 arguments");
    }
    for (int index = 0; index < count; index++) {
        if (args[index].tag != BUN_INT) {
            bun_throw("range() expects integer arguments");
        }
    }
    int64_t start = count == 1 ? 0 : args[0].as.i;
    int64_t stop = count == 1 ? args[0].as.i : args[1].as.i;
    int64_t step = count == 3 ? args[2].as.i : 1;
    if (step == 0) {
        bun_throw("range() step argument must not be zero");
    }
    BunValue result = bun_list_new();
    int64_t length = step > 0 ? (stop - start + step - 1) / step
                              : (start - stop - step - 1) / (-step);
    if (length > 0) {
        bun_list_reserve(result.as.obj, (size_t)length);
    }
    if (step > 0) {
        for (int64_t at = start; at < stop; at += step) {
            bun_list_push(result.as.obj, bun_int_value(at));
        }
    } else {
        for (int64_t at = start; at > stop; at += step) {
            bun_list_push(result.as.obj, bun_int_value(at));
        }
    }
    return result;
}

static BunValue bun_builtin_chr(BunValue *args, int count) {
    if (count != 1 || args[0].tag != BUN_INT) {
        bun_throw("chr() expects an int");
    }
    int64_t code = args[0].as.i;
    if (code < 0 || code > 0x10FFFF) {
        bun_throw("chr() argument out of range");
    }
    char out[5];
    int size = 0;
    unsigned int value = (unsigned int)code;
    if (value < 0x80) {
        out[size++] = (char)value;
    } else if (value < 0x800) {
        out[size++] = (char)(0xC0 | (value >> 6));
        out[size++] = (char)(0x80 | (value & 0x3F));
    } else if (value < 0x10000) {
        out[size++] = (char)(0xE0 | (value >> 12));
        out[size++] = (char)(0x80 | ((value >> 6) & 0x3F));
        out[size++] = (char)(0x80 | (value & 0x3F));
    } else {
        out[size++] = (char)(0xF0 | (value >> 18));
        out[size++] = (char)(0x80 | ((value >> 12) & 0x3F));
        out[size++] = (char)(0x80 | ((value >> 6) & 0x3F));
        out[size++] = (char)(0x80 | (value & 0x3F));
    }
    return bun_str_new(out, (size_t)size);
}

/* ------------------------------------------------------------------ */
/* The files                                                            */
/* ------------------------------------------------------------------ */

/* The path of a file is a string, the same way the machine wants it. */
static const char *bun_file_path(const char *name, BunValue value) {
    if (value.tag != BUN_STR) {
        bun_throw("%s() expects a string path", name);
    }
    return value.as.obj->data;
}

static BunValue bun_builtin_read_file(BunValue *args, int count) {
    if (count != 1) {
        bun_throw("read_file() expects 1 argument, got %d", count);
    }
    const char *path = bun_file_path("read_file", args[0]);
    FILE *handle = fopen(path, "rb");
    if (handle == NULL) {
        bun_throw("cannot read '%s': %s", path, strerror(errno));
    }
    size_t size = 0;
    size_t room = 4096;
    char *data = (char *)bun_alloc(room);
    for (;;) {
        if (size + 1 >= room) {
            room = room * 2;
            char *bigger = (char *)bun_alloc(room);
            memcpy(bigger, data, size);
            data = bigger;
        }
        size_t got = fread(data + size, 1, room - size - 1, handle);
        size += got;
        if (got == 0) {
            break;
        }
    }
    fclose(handle);
    data[size] = '\0';
    return bun_str_new(data, size);
}

static void bun_write_file(BunValue *args, int count, const char *name,
                            const char *mode) {
    if (count != 2) {
        bun_throw("%s() expects 2 arguments, got %d", name, count);
    }
    const char *path = bun_file_path(name, args[0]);
    if (args[1].tag != BUN_STR) {
        bun_throw("%s() expects a string", name);
    }
    FILE *handle = fopen(path, mode);
    if (handle == NULL) {
        bun_throw("cannot write '%s': %s", path, strerror(errno));
    }
    BunObj *text = args[1].as.obj;
    if (text->len > 0) {
        fwrite(text->data, 1, text->len, handle);
    }
    fclose(handle);
}

static BunValue bun_builtin_write_file(BunValue *args, int count) {
    bun_write_file(args, count, "write_file", "wb");
    return bun_null_value();
}

static BunValue bun_builtin_append_file(BunValue *args, int count) {
    bun_write_file(args, count, "append_file", "ab");
    return bun_null_value();
}

static BunValue bun_builtin_file_exists(BunValue *args, int count) {
    if (count != 1) {
        bun_throw("file_exists() expects 1 argument, got %d", count);
    }
    const char *path = bun_file_path("file_exists", args[0]);
    FILE *handle = fopen(path, "rb");
    if (handle == NULL) {
        return bun_bool_value(0);
    }
    fclose(handle);
    return bun_bool_value(1);
}

static BunValue bun_builtin_getenv(BunValue *args, int count) {
    if (count != 1) {
        bun_throw("getenv() expects 1 argument, got %d", count);
    }
    if (args[0].tag != BUN_STR) {
        bun_throw("getenv() expects a string name");
    }
    const char *value = getenv(args[0].as.obj->data);
    if (value == NULL) {
        return bun_null_value();
    }
    return bun_str_from_c(value);
}

static BunValue bun_builtin_ord(BunValue *args, int count) {
    if (count != 1 || args[0].tag != BUN_STR) {
        bun_throw("ord() expects a string");
    }
    BunObj *text = args[0].as.obj;
    if (text->len != 1) {
        bun_throw("ord() expects a single character string");
    }
    unsigned char first = (unsigned char)text->data[0];
    if (first < 0x80) {
        return bun_int_value(first);
    }
    int extra = 0;
    unsigned int code = 0;
    if ((first & 0xE0) == 0xC0) {
        extra = 1;
        code = first & 0x1Fu;
    } else if ((first & 0xF0) == 0xE0) {
        extra = 2;
        code = first & 0x0Fu;
    } else if ((first & 0xF8) == 0xF0) {
        extra = 3;
        code = first & 0x07u;
    } else {
        bun_throw("ord() expects a single character string");
    }
    for (int index = 1; index <= extra; index++) {
        code = (code << 6) | ((unsigned char)text->data[index] & 0x3Fu);
    }
    return bun_int_value((int64_t)code);
}

static void bun_define_builtin(BunEnv *env, const char *name,
                               BunBuiltinFn fn) {
    bun_env_define(env, name, bun_make_builtin(name, fn), 0);
}

/* ------------------------------------------------------------------ */
/* The methods                                                         */
/* ------------------------------------------------------------------ */

static void bun_arity(const char *name, int count, int expected) {
    if (count != expected) {
        bun_throw("'%s' expects %d argument(s), got %d", name, expected, count);
    }
}

static void bun_check_str(const char *name, BunValue value) {
    if (value.tag != BUN_STR) {
        bun_throw("'%s' expects a string argument", name);
    }
}

static void bun_check_int(const char *name, BunValue value) {
    if (value.tag != BUN_INT) {
        bun_throw("'%s' expects an integer argument", name);
    }
}

static BunValue bun_method_call(BunValue receiver, const char *method,
                                BunValue *args, int count) {
    if (receiver.tag == BUN_STRUCT) {
        /* A method of a struct borrows the receiver: the mutation of a
         * field through `self` is seen by the caller. */
        BunObj *object = receiver.as.obj;
        BunEnv *closure = NULL;
        BunFn fn = bun_find_struct_method(object->name, method, &closure);
        if (fn == NULL) {
            bun_throw("unknown method '%s' on %s", method, object->name);
        }
        BunValue call_args[count + 1];
        call_args[0] = receiver;
        for (int index = 0; index < count; index++) {
            call_args[index + 1] = args[index];
        }
        return fn(closure, call_args, count + 1, bun_null_value());
    }
    if (receiver.tag == BUN_STR) {
        BunObj *text = receiver.as.obj;

        switch (method[0]) {
        case 't':
            if (strcmp(method, "trim") == 0) {
                bun_arity(method, count, 0);
                size_t start = 0;
                size_t end = text->len;
                while (start < end && isspace((unsigned char)text->data[start])) {
                    start++;
                }
                while (end > start && isspace((unsigned char)text->data[end - 1])) {
                    end--;
                }
                return bun_str_new(text->data + start, end - start);
            }
            break;
        case 'l':
            if (strcmp(method, "lower") == 0) {
                bun_arity(method, count, 0);
                char *out = (char *)bun_alloc(text->len + 1);
                for (size_t index = 0; index < text->len; index++) {
                    out[index] = (char)tolower((unsigned char)text->data[index]);
                }
                out[text->len] = '\0';
                return bun_str_new(out, text->len);
            }
            if (strcmp(method, "len") == 0) {
                bun_arity(method, count, 0);
                return bun_int_value((int64_t)text->len);
            }
            break;
        case 'u':
            if (strcmp(method, "upper") == 0) {
                bun_arity(method, count, 0);
                char *out = (char *)bun_alloc(text->len + 1);
                for (size_t index = 0; index < text->len; index++) {
                    out[index] = (char)toupper((unsigned char)text->data[index]);
                }
                out[text->len] = '\0';
                return bun_str_new(out, text->len);
            }
            break;
        case 's':
            if (strcmp(method, "split") == 0) {
                bun_arity(method, count, 1);
                bun_check_str(method, args[0]);
                BunObj *separator = args[0].as.obj;
                if (separator->len == 0) {
                    bun_throw("'split' expects a non-empty separator");
                }
                BunValue result = bun_list_new();
                size_t start = 0;
                for (size_t index = 0; index + separator->len <= text->len; index++) {
                    if (memcmp(text->data + index, separator->data,
                               separator->len) == 0) {
                        bun_list_push(result.as.obj,
                                      bun_str_new(text->data + start, index - start));
                        start = index + separator->len;
                        index += separator->len - 1;
                    }
                }
                bun_list_push(result.as.obj,
                              bun_str_new(text->data + start, text->len - start));
                return result;
            }
            if (strcmp(method, "starts_with") == 0) {
                bun_arity(method, count, 1);
                bun_check_str(method, args[0]);
                BunObj *prefix = args[0].as.obj;
                if (prefix->len > text->len) {
                    return bun_bool_value(0);
                }
                return bun_bool_value(memcmp(text->data, prefix->data,
                                             prefix->len) == 0);
            }
            if (strcmp(method, "slice") == 0) {
                bun_arity(method, count, 2);
                bun_check_int(method, args[0]);
                bun_check_int(method, args[1]);
                return bun_slice(receiver, args[0], args[1], bun_null_value());
            }
            break;
        case 'c':
            if (strcmp(method, "contains") == 0) {
                bun_arity(method, count, 1);
                bun_check_str(method, args[0]);
                BunObj *needle = args[0].as.obj;
                if (needle->len == 0) {
                    return bun_bool_value(1);
                }
                for (size_t index = 0; index + needle->len <= text->len; index++) {
                    if (memcmp(text->data + index, needle->data, needle->len) == 0) {
                        return bun_bool_value(1);
                    }
                }
                return bun_bool_value(0);
            }
            break;
        case 'e':
            if (strcmp(method, "ends_with") == 0) {
                bun_arity(method, count, 1);
                bun_check_str(method, args[0]);
                BunObj *suffix = args[0].as.obj;
                if (suffix->len > text->len) {
                    return bun_bool_value(0);
                }
                return bun_bool_value(memcmp(text->data + text->len - suffix->len,
                                             suffix->data, suffix->len) == 0);
            }
            break;
        case 'r':
            if (strcmp(method, "replace") == 0) {
                bun_arity(method, count, 2);
                bun_check_str(method, args[0]);
                bun_check_str(method, args[1]);
                BunObj *needle = args[0].as.obj;
                BunObj *replacement = args[1].as.obj;
                BunValue result = bun_str_new("", 0);
                size_t start = 0;
                if (needle->len == 0) {
                    for (size_t index = 0; index < text->len; index++) {
                        result = bun_str_concat(result,
                            bun_str_new(text->data + index, 1));
                        result = bun_str_concat(result, args[1]);
                    }
                    return result;
                }
                for (size_t index = 0; index + needle->len <= text->len; index++) {
                    if (memcmp(text->data + index, needle->data, needle->len) == 0) {
                        result = bun_str_concat(result,
                            bun_str_new(text->data + start, index - start));
                        result = bun_str_concat(result, args[1]);
                        start = index + needle->len;
                        index += needle->len - 1;
                    }
                }
                result = bun_str_concat(result,
                    bun_str_new(text->data + start, text->len - start));
                return result;
            }
            if (strcmp(method, "repeat") == 0) {
                bun_arity(method, count, 1);
                bun_check_int(method, args[0]);
                int64_t number = args[0].as.i;
                if (number < 0) {
                    bun_throw("'repeat' expects a non-negative count");
                }
                if (number >= 100000) {
                    bun_throw("'repeat' count is too large");
                }
                BunValue result = bun_str_new("", 0);
                for (int64_t index = 0; index < number; index++) {
                    result = bun_str_concat(result, receiver);
                }
                return result;
            }
            break;
        case 'i':
            if (strcmp(method, "index_of") == 0) {
                bun_arity(method, count, 1);
                bun_check_str(method, args[0]);
                BunObj *needle = args[0].as.obj;
                for (size_t index = 0; index + needle->len <= text->len; index++) {
                    if (memcmp(text->data + index, needle->data, needle->len) == 0) {
                        return bun_int_value((int64_t)index);
                    }
                }
                return bun_int_value(-1);
            }
            break;
        default:
            break;
        }
        bun_throw("unknown method '%s' on string", method);
    }
    if (receiver.tag == BUN_LIST) {
        BunObj *list = receiver.as.obj;

        switch (method[0]) {
        case 'p':
            if (strcmp(method, "push") == 0) {
                bun_arity(method, count, 1);
                bun_list_push(list, args[0]);
                return bun_null_value();
            }
            if (strcmp(method, "pop") == 0) {
                bun_arity(method, count, 0);
                if (list->count == 0) {
                    bun_throw("'pop' on an empty list");
                }
                BunValue item = list->items[list->count - 1];
                list->count--;
                return item;
            }
            break;
        case 's':
            if (strcmp(method, "shift") == 0) {
                bun_arity(method, count, 0);
                if (list->count == 0) {
                    bun_throw("'shift' on an empty list");
                }
                BunValue item = list->items[0];
                for (size_t index = 1; index < list->count; index++) {
                    list->items[index - 1] = list->items[index];
                }
                list->count--;
                return item;
            }
            if (strcmp(method, "slice") == 0) {
                bun_arity(method, count, 2);
                bun_check_int(method, args[0]);
                bun_check_int(method, args[1]);
                return bun_slice(receiver, args[0], args[1], bun_null_value());
            }
            if (strcmp(method, "sort") == 0) {
                bun_arity(method, count, 0);
                int numbers = 0;
                int strings = 0;
                for (size_t index = 0; index < list->count; index++) {
                    BunValue item = list->items[index];
                    if (item.tag == BUN_STR) {
                        strings++;
                    } else if (item.tag == BUN_INT || item.tag == BUN_FLOAT) {
                        numbers++;
                    } else {
                        bun_throw("cannot sort list with mixed types");
                    }
                }
                if (numbers && strings) {
                    bun_throw("cannot sort list with mixed types");
                }
                for (size_t index = 1; index < list->count; index++) {
                    BunValue item = list->items[index];
                    size_t at = index;
                    while (at > 0 && bun_truthy(bun_compare(list->items[at - 1],
                                                           item, 2))) {
                        list->items[at] = list->items[at - 1];
                        at--;
                    }
                    list->items[at] = item;
                }
                return bun_null_value();
            }
            if (strcmp(method, "splice") == 0) {
                bun_arity(method, count, 2);
                bun_check_int(method, args[0]);
                bun_check_int(method, args[1]);
                int64_t start = args[0].as.i;
                int64_t amount = args[1].as.i;
                if (start < 0) {
                    start = (int64_t)list->count + start;
                    if (start < 0) {
                        start = 0;
                    }
                }
                if (start > (int64_t)list->count) {
                    start = (int64_t)list->count;
                }
                if (amount < 0) {
                    amount = 0;
                }
                if (start + amount > (int64_t)list->count) {
                    amount = (int64_t)list->count - start;
                }
                BunValue removed = bun_list_new();
                for (int64_t index = 0; index < amount; index++) {
                    bun_list_push(removed.as.obj, list->items[start + index]);
                }
                for (size_t index = (size_t)(start + amount); index < list->count;
                     index++) {
                    list->items[index - (size_t)amount] = list->items[index];
                }
                list->count -= (size_t)amount;
                return removed;
            }
            break;
        case 'l':
            if (strcmp(method, "len") == 0) {
                bun_arity(method, count, 0);
                return bun_int_value((int64_t)list->count);
            }
            break;
        case 'j':
            if (strcmp(method, "join") == 0) {
                bun_arity(method, count, 1);
                bun_check_str(method, args[0]);
                BunObj *separator = args[0].as.obj;
                BunValue result = bun_str_new("", 0);
                for (size_t index = 0; index < list->count; index++) {
                    if (index) {
                        result = bun_str_concat(result, args[0]);
                    }
                    result = bun_str_concat(result,
                        bun_str_from_c(bun_stringify(list->items[index])));
                }
                (void)separator;
                return result;
            }
            break;
        case 'c':
            if (strcmp(method, "contains") == 0) {
                bun_arity(method, count, 1);
                for (size_t index = 0; index < list->count; index++) {
                    if (bun_values_equal(list->items[index], args[0])) {
                        return bun_bool_value(1);
                    }
                }
                return bun_bool_value(0);
            }
            break;
        case 'r':
            if (strcmp(method, "reverse") == 0) {
                bun_arity(method, count, 0);
                BunValue result = bun_list_new();
                for (size_t index = list->count; index > 0; index--) {
                    bun_list_push(result.as.obj, list->items[index - 1]);
                }
                return result;
            }
            break;
        case 'i':
            if (strcmp(method, "insert") == 0) {
                bun_arity(method, count, 2);
                bun_check_int(method, args[0]);
                int64_t index = args[0].as.i;
                if (index < 0) {
                    index = (int64_t)list->count + index;
                    if (index < 0) {
                        index = 0;
                    }
                }
                if (index > (int64_t)list->count) {
                    index = (int64_t)list->count;
                }
                bun_list_push(list, bun_null_value());
                for (size_t at = list->count - 1; at > (size_t)index; at--) {
                    list->items[at] = list->items[at - 1];
                }
                list->items[index] = args[1];
                return bun_null_value();
            }
            break;
        default:
            break;
        }
        bun_throw("unknown method '%s' on list", method);
    }
    if (receiver.tag == BUN_DICT) {
        BunObj *dict = receiver.as.obj;

        switch (method[0]) {
        case 'l':
            if (strcmp(method, "len") == 0) {
                bun_arity(method, count, 0);
                return bun_int_value((int64_t)dict->count);
            }
            break;
        case 'h':
            if (strcmp(method, "has") == 0) {
                bun_arity(method, count, 1);
                return bun_bool_value(bun_dict_has(dict, args[0]));
            }
            break;
        case 'g':
            if (strcmp(method, "get") == 0) {
                bun_arity(method, count, 1);
                return bun_dict_get(dict, args[0]);
            }
            break;
        case 's':
            if (strcmp(method, "set") == 0) {
                bun_arity(method, count, 2);
                bun_dict_set(dict, args[0], args[1]);
                return receiver;
            }
            break;
        case 'u':
            if (strcmp(method, "update") == 0) {
                bun_arity(method, count, 1);
                if (args[0].tag != BUN_DICT) {
                    bun_throw("update() expects a dict");
                }
                BunObj *other = args[0].as.obj;
                for (size_t index = 0; index < other->count; index++) {
                    bun_dict_set(dict, other->keys[index], other->values[index]);
                }
                return receiver;
            }
            break;
        case 'k':
            if (strcmp(method, "keys") == 0) {
                bun_arity(method, count, 0);
                BunValue result = bun_list_new();
                for (size_t index = 0; index < dict->count; index++) {
                    bun_list_push(result.as.obj, dict->keys[index]);
                }
                return result;
            }
            break;
        case 'v':
            if (strcmp(method, "values") == 0) {
                bun_arity(method, count, 0);
                BunValue result = bun_list_new();
                for (size_t index = 0; index < dict->count; index++) {
                    bun_list_push(result.as.obj, dict->values[index]);
                }
                return result;
            }
            break;
        case 'r':
            if (strcmp(method, "remove") == 0) {
                bun_arity(method, count, 1);
                bun_dict_remove(dict, args[0]);
                return bun_null_value();
            }
            break;
        default:
            break;
        }
        bun_throw("unknown method '%s' on dict", method);
    }
    if (receiver.tag == BUN_SET) {
        BunObj *set = receiver.as.obj;

        switch (method[0]) {
        case 'l':
            if (strcmp(method, "len") == 0) {
                bun_arity(method, count, 0);
                return bun_int_value((int64_t)set->count);
            }
            break;
        case 'a':
            if (strcmp(method, "add") == 0) {
                bun_arity(method, count, 1);
                bun_set_add(set, args[0]);
                return receiver;
            }
            break;
        case 'r':
            if (strcmp(method, "remove") == 0) {
                bun_arity(method, count, 1);
                bun_set_remove(set, args[0]);
                return bun_null_value();
            }
            break;
        case 'c':
            if (strcmp(method, "contains") == 0) {
                bun_arity(method, count, 1);
                bun_check_key(args[0]);
                return bun_bool_value(bun_set_find(set, args[0]) >= 0);
            }
            break;
        case 'v':
            if (strcmp(method, "values") == 0) {
                bun_arity(method, count, 0);
                return bun_set_values(set);
            }
            break;
        case 'u':

        case 'i':

        case 'd':
            if (strcmp(method, "union") == 0 ||
                strcmp(method, "intersection") == 0 ||
                strcmp(method, "difference") == 0) {
                bun_arity(method, count, 1);
                if (args[0].tag != BUN_SET) {
                    bun_throw("%s() expects a set", method);
                }
                BunObj *other = args[0].as.obj;
                if (strcmp(method, "union") == 0) {
                    return bun_set_union(set, other);
                }
                if (strcmp(method, "intersection") == 0) {
                    return bun_set_intersection(set, other);
                }
                return bun_set_difference(set, other);
            }
            break;
        default:
            break;
        }
        bun_throw("unknown method '%s' on set", method);
    }
    if (receiver.tag == BUN_SECRET) {
        if (strcmp(method, "reveal") == 0) {
            bun_arity(method, count, 0);
            return receiver.as.obj->secret;
        }
        bun_throw("unknown method '%s' on secret", method);
    }
    bun_throw("'%s' is not a method on %s", method, bun_type_name(receiver));
    return bun_null_value();
}

/* ------------------------------------------------------------------ */
/* The binding of the arguments                                        */
/* ------------------------------------------------------------------ */

static void bun_bind_one(BunEnv *env, BunValue *slots,
                          const BunParam *param, BunValue value) {
    /* The arguments of a call are copied, because a struct is a value
     * type.  The receiver of a method is borrowed, and it is not
     * copied. */
    if (!param->borrowed) {
        value = bun_copy_value(value);
    }
    if (slots != NULL && param->slot >= 0) {
        slots[param->slot] = value;
        return;
    }
    bun_env_set(env, param->name, value, 1);
}

/* The slow path of the binding of the arguments.  It is not inlined
   into the program, because the program has its own path for the calls
   that are plain, and the slow path would take the room of the frame. */
#if defined(__GNUC__)
__attribute__((noinline))
#endif
static void bun_bind_parameters(BunEnv *env, const char *name,
                                const BunParam *params, int count,
                                BunValue *args, int argc, BunValue kwargs,
                                BunValue *slots) {
    int positional = 0;
    const BunParam *vararg = NULL;
    const BunParam *kwarg = NULL;
    for (int index = 0; index < count; index++) {
        if (params[index].kind == 0) {
            positional++;
        } else if (params[index].kind == 1) {
            vararg = &params[index];
        } else if (params[index].kind == 2) {
            kwarg = &params[index];
        }
    }
    if (argc > positional && vararg == NULL) {
        bun_throw("function '%s' expects %d argument(s), got %d", name,
                  positional, argc);
    }
    int position = 0;
    for (int index = 0; index < count; index++) {
        const BunParam *param = &params[index];
        if (param->kind == 1) {
            BunValue list = bun_list_new();
            for (int item = positional; item < argc; item++) {
                bun_list_push(list.as.obj, args[item]);
            }
            bun_bind_one(env, slots, param, list);
            continue;
        }
        if (param->kind == 2) {
            BunValue dict = bun_dict_new();
            if (kwargs.tag == BUN_DICT) {
                BunObj *given = kwargs.as.obj;
                for (size_t item = 0; item < given->count; item++) {
                    int known = 0;
                    for (int other = 0; other < count; other++) {
                        if (params[other].kind == 2) {
                            continue;
                        }
                        if (bun_values_equal(given->keys[item],
                                             bun_str_from_c(params[other].name))) {
                            known = 1;
                            break;
                        }
                    }
                    if (!known) {
                        bun_dict_set(dict.as.obj, given->keys[item],
                                     given->values[item]);
                    }
                }
            }
            bun_bind_one(env, slots, param, dict);
            continue;
        }
        BunValue value;
        int given = 0;
        if (param->kind == 0 && position < argc) {
            /* A name that is given twice is a failure of the call: once
             * as a positional argument and once as a keyword. */
            if (kwargs.tag == BUN_DICT) {
                BunObj *dict = kwargs.as.obj;
                BunValue key = bun_str_from_c(param->name);
                if (bun_dict_has(dict, key)) {
                    bun_throw("function '%s' got multiple values for argument "
                              "'%s'", name, param->name);
                }
            }
            value = args[position];
            given = 1;
            position++;
        } else if (kwargs.tag == BUN_DICT) {
            BunObj *dict = kwargs.as.obj;
            BunValue key = bun_str_from_c(param->name);
            if (bun_dict_has(dict, key)) {
                value = bun_dict_get(dict, key);
                given = 1;
            }
        }
        if (given) {
            bun_bind_one(env, slots, param, value);
            continue;
        }
        if (param->has_default) {
            bun_bind_one(env, slots, param, param->default_code(env, NULL, 0,
                                                                bun_null_value()));
            continue;
        }
        bun_throw("function '%s' missing required argument '%s'", name,
                  param->name);
    }
    if (kwarg == NULL && kwargs.tag == BUN_DICT) {
        /* A keyword the function does not have is a failure of the call.
         * The name in the message is the smallest one, like the machine. */
        BunObj *dict = kwargs.as.obj;
        const char *smallest = NULL;
        for (size_t item = 0; item < dict->count; item++) {
            BunValue key = dict->keys[item];
            int known = 0;
            if (key.tag != BUN_STR) {
                continue;
            }
            for (int other = 0; other < count; other++) {
                if (params[other].kind == 2) {
                    continue;
                }
                if (strcmp(key.as.obj->data, params[other].name) == 0) {
                    known = 1;
                    break;
                }
            }
            if (known) {
                continue;
            }
            if (smallest == NULL || strcmp(key.as.obj->data, smallest) < 0) {
                smallest = key.as.obj->data;
            }
        }
        if (smallest != NULL) {
            bun_throw("function '%s' got an unexpected keyword argument '%s'",
                      name, smallest);
        }
    }
}

/* ------------------------------------------------------------------ */
/* The calls                                                           */
/* ------------------------------------------------------------------ */

static BunValue bun_call(BunValue callee, BunValue *args, int count,
                          BunValue kwargs) {
    if (callee.tag == BUN_FUNC) {
        BunObj *object = callee.as.obj;
        BunEnv *env = object->closure;
        if (object->needs_env) {
            env = bun_env_new(env);
        }
        return object->fn(env, args, count, kwargs);
    }
    if (callee.tag == BUN_BUILTIN) {
        if (kwargs.tag == BUN_DICT && kwargs.as.obj->count > 0) {
            bun_throw("builtin '%s' does not accept keyword arguments",
                      callee.as.obj->name);
        }
        return callee.as.obj->builtin(args, count);
    }
    bun_throw("%s is not callable", bun_stringify(callee));
    return bun_null_value();
}

static BunIter bun_iter_new(BunValue value) {
    BunIter iter;
    iter.count = 0;
    iter.at = 0;
    iter.is_string = 0;
    iter.text = NULL;
    iter.items = NULL;
    iter.is_object = 0;
    iter.object = value;
    if (value.tag == BUN_LIST) {
        iter.items = value.as.obj->items;
        iter.count = value.as.obj->count;
    } else if (value.tag == BUN_SET) {
        iter.items = value.as.obj->items;
        iter.count = value.as.obj->count;
    } else if (value.tag == BUN_DICT) {
        iter.items = value.as.obj->keys;
        iter.count = value.as.obj->count;
    } else if (value.tag == BUN_STR) {
        iter.is_string = 1;
        iter.text = value.as.obj;
        iter.count = value.as.obj->len;
    } else if (value.tag == BUN_STRUCT) {
        /* A value of a struct is an iterator when it has a `next`
           method: the method answers with an option, a `some` is the
           next item and a `none` is the end of the sequence. */
        BunObj *object = value.as.obj;
        if (bun_find_struct_method(object->name, "next", NULL) == NULL) {
            bun_throw("value is not iterable");
        }
        iter.is_object = 1;
    } else {
        bun_throw("value is not iterable");
    }
    return iter;
}

static int bun_iter_next(BunIter *iter, BunValue *out) {
    if (iter->is_object) {
        BunValue step = bun_method_call(iter->object, "next", NULL, 0);
        if (step.tag != BUN_DICT) {
            bun_throw("the 'next' method has to answer with an option");
        }
        if (bun_dict_has(step.as.obj, bun_str_from_c("some"))) {
            *out = bun_dict_get_c(step.as.obj, "some");
            return 1;
        }
        return 0;
    }
    if (iter->at >= iter->count) {
        return 0;
    }
    if (iter->is_string) {
        *out = bun_str_new(iter->text->data + iter->at, 1);
    } else {
        *out = iter->items[iter->at];
    }
    iter->at++;
    return 1;
}

/* ------------------------------------------------------------------ */
/* The tasks and the groups                                            */
/* ------------------------------------------------------------------ */

/* A task is the record of a `spawn`: its thread, its answer, its failure
   and the flag of a `cancel`.  A group is the record of a `scope`: the
   tasks that were spawned while the group was open.  A task of the group
   is joined before the scope ends, and the first failure of a child is
   the failure of the scope. */

typedef struct BunTask {
    int id;
    pthread_t thread;
    int started;
    int done;
    int cancelled;
    int has_error;
    BunValue error;
    BunValue result;
    BunValue function;
    struct BunGroup *group;
} BunTask;

typedef struct BunGroup {
    BunTask **items;
    int count;
    int size;
    struct BunGroup *previous;
} BunGroup;

#define BUN_MAX_TASKS 4096

static BunTask *bun_task_registry[BUN_MAX_TASKS];
static int bun_task_count = 0;
static pthread_mutex_t bun_task_lock = PTHREAD_MUTEX_INITIALIZER;
static _Thread_local BunGroup *bun_current_group = NULL;
static _Thread_local BunTask *bun_current_task = NULL;

static BunTask *bun_task_new(BunValue function) {
    BunTask *task = (BunTask *)bun_alloc(sizeof(BunTask));
    task->id = 0;
    task->started = 0;
    task->done = 0;
    task->cancelled = 0;
    task->has_error = 0;
    task->error = bun_null_value();
    task->result = bun_null_value();
    task->function = function;
    task->group = bun_current_group;
    return task;
}

/* The task is registered in the registry of the program and, while a
   group is open, in the group of the scope.  The two lists are guarded:
   the program joins a task while another task is still running, and a
   task of the group may spawn a task of its own. */
static int bun_task_register(BunTask *task) {
    pthread_mutex_lock(&bun_task_lock);
    if (bun_task_count >= BUN_MAX_TASKS) {
        pthread_mutex_unlock(&bun_task_lock);
        return 0;
    }
    bun_task_registry[bun_task_count++] = task;
    task->id = bun_task_count - 1;
    if (task->group != NULL) {
        if (task->group->count >= task->group->size) {
            int size = task->group->size * 2;
            BunTask **items;
            if (size == 0) {
                size = 4;
            }
            items = (BunTask **)bun_alloc(sizeof(BunTask *) * size);
            if (task->group->count > 0) {
                memcpy(items, task->group->items,
                       sizeof(BunTask *) * task->group->count);
            }
            task->group->items = items;
            task->group->size = size;
        }
        task->group->items[task->group->count++] = task;
    }
    pthread_mutex_unlock(&bun_task_lock);
    return 1;
}

/* Whether a task of the program is still running.  The memory of the
   program is not freed while a task runs, because the task still uses
   the values of the program. */
static int bun_task_running(void) {
    int index;
    int running = 0;
    pthread_mutex_lock(&bun_task_lock);
    for (index = 0; index < bun_task_count; index++) {
        BunTask *task = bun_task_registry[index];
        if (task->started && !task->done) {
            running = 1;
            break;
        }
    }
    pthread_mutex_unlock(&bun_task_lock);
    return running;
}

static BunTask *bun_task_lookup(BunValue handle) {
    int number;
    if (handle.tag != BUN_DICT) {
        return NULL;
    }
    {
        BunValue id = bun_dict_get_c(handle.as.obj, "id");
        if (id.tag != BUN_INT) {
            return NULL;
        }
        number = (int)id.as.i;
    }
    pthread_mutex_lock(&bun_task_lock);
    if (number < 0 || number >= bun_task_count) {
        pthread_mutex_unlock(&bun_task_lock);
        return NULL;
    }
    {
        BunTask *task = bun_task_registry[number];
        pthread_mutex_unlock(&bun_task_lock);
        return task;
    }
}

/* The body of a task runs on a thread of its own.  An error of the body
   is an error of the task: the place of the failure is kept, and the task
   that joins it sees the failure instead of an answer. */
static void *bun_task_thread(void *data) {
    BunTask *task = (BunTask *)data;
    BunHandler handler;
    handler.kind = 0;
    handler.env = NULL;
    handler.prev = NULL;
    bun_current_task = task;
    bun_current_group = task->group;
    bun_arena_init_thread();
    if (setjmp(handler.buf) == 0) {
        bun_handler = &handler;
        task->result = bun_call(task->function, NULL, 0, bun_null_value());
        bun_handler = handler.prev;
    } else {
        task->has_error = 1;
        task->error = bun_str_from_c(bun_error_message);
    }
    /* The values of the task move to the list of the ended tasks before
       the task says that it is done, so the task that joins it never
       sees a value that is gone. */
    bun_arena_migrate();
    task->done = 1;
    return NULL;
}

static BunValue bun_builtin_spawn(BunValue *args, int count) {
    BunTask *task;
    if (count != 1) {
        bun_throw("spawn() expects 1 argument");
    }
    if (args[0].tag != BUN_FUNC) {
        bun_throw("spawn() expects a function");
    }
    task = bun_task_new(args[0]);
    if (!bun_task_register(task)) {
        bun_throw("too many tasks");
    }
    if (pthread_create(&task->thread, NULL, bun_task_thread, task) != 0) {
        bun_throw("cannot start a task");
    }
    task->started = 1;
    {
        BunValue handle = bun_dict_new();
        bun_dict_set(handle.as.obj, bun_str_from_c("id"),
                     bun_int_value(task->id));
        return handle;
    }
}

static BunTask *bun_task_handle(BunValue *args, int count, const char *name) {
    if (count != 1) {
        bun_throw("%s() expects 1 argument", name);
    }
    {
        BunTask *task = bun_task_lookup(args[0]);
        if (task == NULL) {
            bun_throw("%s() expects a task handle", name);
        }
        return task;
    }
}

static void bun_task_join(BunTask *task) {
    if (task->started && pthread_equal(task->thread, pthread_self()) == 0) {
        pthread_join(task->thread, NULL);
        task->started = 0;
    }
}

static BunValue bun_builtin_task_join(BunValue *args, int count) {
    BunTask *task = bun_task_handle(args, count, "task_join");
    bun_task_join(task);
    if (task->has_error) {
        bun_throw("%s", task->error.as.obj->data);
    }
    return task->result;
}

static BunValue bun_builtin_task_done(BunValue *args, int count) {
    BunTask *task = bun_task_handle(args, count, "task_done");
    return bun_bool_value(task->done);
}

static BunValue bun_builtin_cancel(BunValue *args, int count) {
    BunTask *task = bun_task_handle(args, count, "cancel");
    task->cancelled = 1;
    return bun_null_value();
}

static BunValue bun_builtin_task_cancelled(BunValue *args, int count) {
    if (count == 0) {
        return bun_bool_value(bun_current_task != NULL &&
                              bun_current_task->cancelled);
    }
    if (count != 1) {
        bun_throw("task_cancelled() expects no argument or a task handle");
    }
    {
        BunTask *task = bun_task_lookup(args[0]);
        if (task == NULL) {
            bun_throw("task_cancelled() expects a task handle");
        }
        return bun_bool_value(task->cancelled);
    }
}

static BunValue bun_builtin_sleep(BunValue *args, int count) {
    double seconds;
    struct timespec request;
    if (count != 1) {
        bun_throw("sleep() expects 1 argument");
    }
    if (args[0].tag == BUN_INT) {
        seconds = (double)args[0].as.i;
    } else if (args[0].tag == BUN_FLOAT) {
        seconds = args[0].as.f;
    } else {
        bun_throw("sleep() expects a number of seconds");
    }
    if (seconds < 0) {
        bun_throw("sleep() expects a non-negative number");
    }
    request.tv_sec = (time_t)seconds;
    request.tv_nsec = (long)((seconds - (double)request.tv_sec) * 1000000000.0);
    nanosleep(&request, NULL);
    return bun_null_value();
}

/* The scope of the program.  The group is opened before the body runs
   and closed after it: every task of the group is joined, and the first
   failure of a child is raised when the body has no failure of its own. */
static BunGroup *bun_scope_enter(void) {
    BunGroup *group = (BunGroup *)bun_alloc(sizeof(BunGroup));
    group->items = NULL;
    group->count = 0;
    group->size = 0;
    group->previous = bun_current_group;
    bun_current_group = group;
    return group;
}

static void bun_scope_exit(BunPending *pending) {
    BunGroup *group = bun_current_group;
    BunTask **tasks;
    int count;
    int index;
    const char *error = NULL;
    if (group == NULL) {
        bun_throw("'scope' without an open group");
    }
    bun_current_group = group->previous;
    /* The tasks of the group are copied before they are joined: a task of
       the group may spawn a task of its own, and the list of the group
       grows while the group is closed. */
    pthread_mutex_lock(&bun_task_lock);
    count = group->count;
    tasks = (BunTask **)bun_alloc(sizeof(BunTask *) * (count > 0 ? count : 1));
    if (count > 0) {
        memcpy(tasks, group->items, sizeof(BunTask *) * count);
    }
    pthread_mutex_unlock(&bun_task_lock);
    for (index = 0; index < count; index++) {
        BunTask *task = tasks[index];
        bun_task_join(task);
        if (error == NULL && task->has_error) {
            error = task->error.as.obj->data;
        }
    }
    if (error != NULL && !pending->has) {
        bun_throw("%s", error);
    }
}

/* ------------------------------------------------------------------ */
/* The entry point of the generated program                             */
/* ------------------------------------------------------------------ */

static BunValue bun_module_code(BunEnv *globals);

int main(int argc, char **argv) {
    (void)argc;
    (void)argv;
    BunEnv *globals = bun_env_new(NULL);
    bun_globals_env = globals;
    bun_define_builtin(globals, "print", bun_builtin_print);
    bun_define_builtin(globals, "len", bun_builtin_len);
    bun_define_builtin(globals, "str", bun_builtin_str);
    bun_define_builtin(globals, "int", bun_builtin_int);
    bun_define_builtin(globals, "float", bun_builtin_float);
    bun_define_builtin(globals, "bool", bun_builtin_bool);
    bun_define_builtin(globals, "type_of", bun_builtin_type_of);
    bun_define_builtin(globals, "abs", bun_builtin_abs);
    bun_define_builtin(globals, "min", bun_builtin_min);
    bun_define_builtin(globals, "max", bun_builtin_max);
    bun_define_builtin(globals, "sum", bun_builtin_sum);
    bun_define_builtin(globals, "any", bun_builtin_any);
    bun_define_builtin(globals, "all", bun_builtin_all);
    bun_define_builtin(globals, "zip", bun_builtin_zip);
    bun_define_builtin(globals, "enumerate", bun_builtin_enumerate);
    bun_define_builtin(globals, "sorted", bun_builtin_sorted);
    bun_define_builtin(globals, "reversed", bun_builtin_reversed);
    bun_define_builtin(globals, "range", bun_builtin_range);
    bun_define_builtin(globals, "chr", bun_builtin_chr);
    bun_define_builtin(globals, "ord", bun_builtin_ord);
    bun_define_builtin(globals, "read_file", bun_builtin_read_file);
    bun_define_builtin(globals, "write_file", bun_builtin_write_file);
    bun_define_builtin(globals, "append_file", bun_builtin_append_file);
    bun_define_builtin(globals, "file_exists", bun_builtin_file_exists);
    bun_define_builtin(globals, "getenv", bun_builtin_getenv);
    bun_define_builtin(globals, "set", bun_builtin_set);
    bun_define_builtin(globals, "secret", bun_builtin_secret);
    bun_define_builtin(globals, "dump", bun_builtin_dump);
    bun_define_builtin(globals, "Ok", bun_builtin_Ok);
    bun_define_builtin(globals, "Err", bun_builtin_Err);
    bun_define_builtin(globals, "is_ok", bun_builtin_is_ok);
    bun_define_builtin(globals, "is_err", bun_builtin_is_err);
    bun_define_builtin(globals, "some", bun_builtin_some);
    bun_define_builtin(globals, "none", bun_builtin_none);
    bun_define_builtin(globals, "is_some", bun_builtin_is_some);
    bun_define_builtin(globals, "is_none", bun_builtin_is_none);
    bun_define_builtin(globals, "spawn", bun_builtin_spawn);
    bun_define_builtin(globals, "task_join", bun_builtin_task_join);
    bun_define_builtin(globals, "task_done", bun_builtin_task_done);
    bun_define_builtin(globals, "cancel", bun_builtin_cancel);
    bun_define_builtin(globals, "task_cancelled", bun_builtin_task_cancelled);
    bun_define_builtin(globals, "sleep", bun_builtin_sleep);
    bun_arena_init_thread();
    BunValue result = bun_module_code(globals);
    (void)result;
    if (!bun_task_running()) {
        bun_arena_release();
    }
    return 0;
}

#endif /* BUN_C_RUNTIME_H */
