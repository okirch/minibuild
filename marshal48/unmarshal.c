/*
Ruby marshal48 - for python

Copyright (C) 2020 SUSE

This program is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, version 2.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License along
with this program; if not, write to the Free Software Foundation, Inc.,
51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
*/

#include <assert.h>
#include <stdarg.h>
#include <Python.h>
#include <structmember.h>

#include "extension.h"
#include "ruby_impl.h"
#include "ruby_utils.h"

typedef struct unmarshal_state {
	ruby_context_t *	ruby;
	ruby_reader_t *		reader;

	struct {
		unsigned int	indent;
		bool		quiet;
	} log;
} unmarshal_state;


static ruby_instance_t *unmarshal_process(unmarshal_state *s);
extern ruby_instance_t *unmarshal_process_quiet(unmarshal_state *s);

static void
__unmarshal_trace(unmarshal_state *s, const char *fmt, ...)
{
	va_list ap;

	va_start(ap, fmt);
	fprintf(stderr, "%*.*s", s->log.indent, s->log.indent, "");
	vfprintf(stderr, fmt, ap);
	fputs("\n", stderr);
	va_end(ap);
}

#define unmarshal_trace(s, fmt ...) do { \
	if (!(s)->log.quiet) \
		__unmarshal_trace(s, ## fmt); \
} while (0)
#define unmarshal_enter(s)	unmarshal_trace(s, "enter %s()", __func__)
#define unmarshal_tp(s)		unmarshal_trace(s, "TP %s:%d", __func__, __LINE__)

#define py_stringify(obj)	PyUnicode_AsUTF8(PyObject_Str(obj))

/*
 * Manage the state object
 */
static void
unmarshal_state_init(unmarshal_state *s, ruby_context_t *ruby, PyObject *io)
{
	memset(s, 0, sizeof(*s));
	s->ruby = ruby;

	s->reader = ruby_reader_new(io);
}

static void
unmarshal_state_destroy(unmarshal_state *s)
{
	/* We do not delete the ruby context; that is done by the caller */
	ruby_reader_free(s->reader);
}

static bool
unmarshal_next_fixnum(unmarshal_state *s, long *fixnump)
{
	ruby_reader_t *reader = s->reader;
	int cc;

	if (!ruby_reader_nextc(reader, &cc))
		return false;

	// unmarshal_trace(s, "int0=0x%x", cc);

	switch (cc) {
	case 0:
		*fixnump = 0;
		return true;
	
	case 1:
	case 2:
	case 3:
		return ruby_reader_nextw(reader, cc, fixnump);

	case 0xff:
		if (!ruby_reader_nextc(reader, &cc))
			return false;
		*fixnump = 1 - cc;
		return true;

	case 0xfe:
	case 0xfd:
	case 0xfc:
		PyErr_Format(PyExc_NotImplementedError, "%s: fixnum format 0x%x not yet implemented", __func__, cc);
		return false;

		if (!ruby_reader_nextw(reader, cc ^ 0xff, fixnump))
			return false;
		*fixnump = -(*fixnump);
		return true;

	default:
		if (cc < 0x80)
			*fixnump = cc - 5;
		else
			*fixnump = 0x80 - cc - 5;
		return true;
	}
}

static bool
__unmarshal_next_byteseq(unmarshal_state *s, ruby_byteseq_t *seq)
{
	ruby_reader_t *reader = s->reader;
	long count;

	if (!unmarshal_next_fixnum(s, &count))
		return false;

	assert(seq->count == 0);
	return ruby_reader_next_byteseq(reader, count, seq);
}

const char *
unmarshal_next_string(unmarshal_state *s, const char *encoding)
{
	static ruby_byteseq_t seq;

	ruby_byteseq_destroy(&seq);
	if (!__unmarshal_next_byteseq(s, &seq))
		return NULL;

	ruby_byteseq_append(&seq, "", 1);

	assert(!strcmp(encoding, "latin1"));
	return (const char *) seq.data;
	/* return PyUnicode_Decode(data, count, encoding, NULL); */
}

/*
 * Simple constants
 */
static ruby_instance_t *
unmarshal_process_none(unmarshal_state *s)
{
	return (ruby_instance_t *) &ruby_None;
}

static ruby_instance_t *
unmarshal_process_true(unmarshal_state *s)
{
	return (ruby_instance_t *) &ruby_True;
}

static ruby_instance_t *
unmarshal_process_false(unmarshal_state *s)
{
	return (ruby_instance_t *) &ruby_False;
}

/*
 * Integers
 */
static ruby_instance_t *
unmarshal_process_int(unmarshal_state *s)
{
	long value;

	if (!(unmarshal_next_fixnum(s, &value)))
		return NULL;

	return ruby_Int_new(s->ruby, value);
}

/*
 * Define symbol
 */
static ruby_instance_t *
unmarshal_define_symbol(unmarshal_state *s, const char *string)
{
	ruby_instance_t *sym = ruby_Symbol_new(s->ruby, string);

	unmarshal_trace(s, "unmarshal_define_symbol(%s) = %d", string, sym->reg.id);
	return sym;
}

/*
 * A symbol is a byte sequence; no character encoding.
 */
static ruby_instance_t *
unmarshal_process_symbol(unmarshal_state *s)
{
	const char *string;

	string = unmarshal_next_string(s, "latin1");
	if (string == NULL)
		return NULL;

	return unmarshal_define_symbol(s, string);
}

static ruby_instance_t *
unmarshal_process_symbol_reference(unmarshal_state *s)
{
	ruby_instance_t *symbol;
	long ref;

	if (!unmarshal_next_fixnum(s, &ref))
		return NULL;

	symbol = ruby_context_get_symbol(s->ruby, ref);
	if (symbol == NULL) {
		fprintf(stderr, "Invalid symbol reference %ld\n", ref);
		return NULL;
	}

	unmarshal_trace(s, "%s(%d) = \"%s\"", __func__, ref, ruby_Symbol_get_name(symbol));
	return symbol;
}

/*
 * Register an object
 */
static void
unmarshal_register_object(unmarshal_state *s, ruby_instance_t *object)
{
	assert(object->reg.id >= 0 && object->reg.kind == RUBY_REG_OBJECT);
	/* simple_object_array_append(&s->objects, object); */
	/* return object; */
}

static ruby_instance_t *
unmarshal_process_object_reference(unmarshal_state *s)
{
	ruby_instance_t *object;
	long ref;

	if (!unmarshal_next_fixnum(s, &ref))
		return NULL;

	object = ruby_context_get_object(s->ruby, ref);
	if (object == NULL) {
		fprintf(stderr, "Invalid object reference %ld\n", ref);
		return NULL;
	}

	unmarshal_trace(s, "Referenced object #%ld: %s", ref, ruby_instance_repr(object));
	return object;
}

/*
 * String processing
 * It would be nice if we could just create a native Python string here.
 * However, the string encoding is often transported as a string object
 * follwed by one instance variable E=True/False.
 * So we need a ruby.String object that understands the set_instance_var
 * protocol.
 */
static ruby_instance_t *
unmarshal_process_string(unmarshal_state *s)
{
	const char *raw_string;
	ruby_instance_t *string = NULL;

	unmarshal_enter(s);

	if (!(raw_string = unmarshal_next_string(s, "latin1")))
		return NULL;

	unmarshal_trace(s, "decoded string \"%s\"", raw_string);

	string = ruby_String_new(s->ruby, raw_string);
	if (string == NULL)
		return NULL;

	/* Register all objects as soon as they get created; this seems to
	 * reflect the order in which the ruby marshal48 code assigns
	 * object IDs */
	unmarshal_register_object(s, string);

	return string;
}

/*
 * Array processing
 */
static ruby_instance_t *
unmarshal_process_array(unmarshal_state *s)
{
	ruby_instance_t *array;
	long i, count;

	if (!unmarshal_next_fixnum(s, &count))
		return NULL;

	unmarshal_trace(s, "Decoding array with %ld objects", count);

	array = ruby_Array_new(s->ruby);
	if (array == NULL)
		return NULL;

	/* Register all objects as soon as they get created; this seems to
	 * reflect the order in which the ruby marshal48 code assigns
	 * object IDs */
	unmarshal_register_object(s, array);

	for (i = 0; i < count; ++i) {
		ruby_instance_t *item;

		item = unmarshal_process(s);
		if (item == NULL)
			return NULL;

		if (!ruby_Array_append(array, item))
			return NULL;
	}

	return array;
}

/*
 * Hash processing
 */
static ruby_instance_t *
unmarshal_process_hash(unmarshal_state *s)
{
	ruby_instance_t *hash;
	long i, count;

	if (!unmarshal_next_fixnum(s, &count))
		return NULL;

	unmarshal_trace(s, "Decoding hash with %ld objects", count);

	hash = ruby_Hash_new(s->ruby);

	/* Register all objects as soon as they get created; this seems to
	 * reflect the order in which the ruby marshal48 code assigns
	 * object IDs */
	unmarshal_register_object(s, hash);

	for (i = 0; i < count; ++i) {
		ruby_instance_t *key, *value;

		key = unmarshal_process(s);
		if (key == NULL)
			return NULL;

		value = unmarshal_process(s);
		if (value == NULL)
			return NULL;

		if (!ruby_Hash_add(hash, key, value))
			return NULL;
	}

	return hash;
}

/*
 * Common helper to create object instances that specify a Classname
 */
static inline ruby_instance_t *
__unmarshal_process_object_class_instance(unmarshal_state *s,
		ruby_instance_t * (*constructor)(ruby_context_t *, const char *))
{
	ruby_instance_t *name_instance, *object;
	char *classname;

	if (!(name_instance = unmarshal_process(s)))
		return NULL;

	classname = ruby_instance_as_string(name_instance);
	if (classname == NULL)
		return NULL;

	object = constructor(s->ruby, classname);
	free(classname);

	if (object == NULL)
		return NULL;

	/* Register all objects as soon as they get created; this seems to
	 * reflect the order in which the ruby marshal48 code assigns
	 * object IDs */
	unmarshal_register_object(s, object);

	return object;
}

/*
 * Common helper function to process instance variables
 */
static inline bool
__unmarshal_process_instance_vars(unmarshal_state *s, ruby_instance_t *object)
{
	long i, count;

	unmarshal_enter(s);
	if (!unmarshal_next_fixnum(s, &count))
		return false;

	unmarshal_trace(s, "%ld instance variables follow", count);

	for (i = 0; i < count; ++i) {
		ruby_instance_t *key, *value;

		key = unmarshal_process(s);
		if (key == NULL)
			return false;

		value = unmarshal_process(s);
		if (value == NULL)
			return false;

		unmarshal_trace(s, "key=%s value=%s", ruby_instance_repr(key), ruby_instance_repr(value));

		if (!ruby_instance_set_var(object, key, value))
			return false;
	}

	return true;
}


/*
 * Arbitrary object, followed by a bunch of instance variables
 */
static ruby_instance_t *
unmarshal_process_object_with_instance_vars(unmarshal_state *s)
{
	ruby_instance_t *object;

	if (!(object = unmarshal_process(s)))
		return NULL;

	/* Do not register the object here. If it *is* a proper object
	 * (rather than say a symbol or fixnum) it has already been
	 * registered inside the call to unmarshal_process() above. */

	if (!__unmarshal_process_instance_vars(s, object)) {
		Py_DECREF(object);
		return NULL;
	}

	return object;
}

/*
 * Generic object, which is constructed as Classname + instance variables
 */
static ruby_instance_t *
unmarshal_process_generic_object(unmarshal_state *s)
{
	ruby_instance_t *object;

	object = __unmarshal_process_object_class_instance(s, ruby_GenericObject_new);
	if (object == NULL)
		return NULL;

	if (!__unmarshal_process_instance_vars(s, object))
		return NULL;

	return object;
}

/*
 * Marshaled object, which is constructed by instantiating Classname() and calling
 * marshal_load() with an unmarshaled ruby object
 */
static ruby_instance_t *
unmarshal_process_user_marshal(unmarshal_state *s)
{
	ruby_instance_t *object, *data;

	object = __unmarshal_process_object_class_instance(s, ruby_UserMarshal_new);
	if (object == NULL)
		return NULL;

	data = unmarshal_process(s);
	if (data == NULL)
		return NULL;

	if (!ruby_UserMarshal_set_data(object, data))
		return NULL;

	return object;
}

/*
 * User Defined object, which is constructed by instantiating Classname() and calling
 * load() with a byte sequence (which may or may not contain marshaled data).
 */
static ruby_instance_t *
unmarshal_process_user_defined(unmarshal_state *s)
{
	ruby_instance_t *object;
	ruby_byteseq_t *data;

	object = __unmarshal_process_object_class_instance(s, ruby_UserDefined_new);
	if (object == NULL)
		return NULL;

	/* Get a pointer to the object's internal byteseq buffer */
	if (!(data = __ruby_UserDefined_get_data_rw(object))) {
		/* complain */
		return NULL;
	}

	/* Clear the byteseq object; read from stream */
	ruby_byteseq_destroy(data);
	if (!__unmarshal_next_byteseq(s, data)) {
		/* complain */
		return NULL;
	}

	return object;
}

static ruby_instance_t *
__unmarshal_process(unmarshal_state *s)
{
	typedef ruby_instance_t *(*unmarshal_process_fn_t)(unmarshal_state *s);
	static unmarshal_process_fn_t unmarshal_process_table[256] = {
		['T'] = unmarshal_process_true,
		['F'] = unmarshal_process_false,
		['0'] = unmarshal_process_none,

		['i'] = unmarshal_process_int,
		[':'] = unmarshal_process_symbol,
		[';'] = unmarshal_process_symbol_reference,
		['@'] = unmarshal_process_object_reference,

		/* The following are all objects that have an object id (and can thus be referenced by ID) */
		['['] = unmarshal_process_array,
		['{'] = unmarshal_process_hash,
		['"'] = unmarshal_process_string,
		['I'] = unmarshal_process_object_with_instance_vars,
		['o'] = unmarshal_process_generic_object,
		['U'] = unmarshal_process_user_marshal,
		['u'] = unmarshal_process_user_defined,
	};
	unmarshal_process_fn_t process_fn;
	int cc;

	if (!ruby_reader_nextc(s->reader, &cc))
		return NULL;

	assert(0 <= cc && cc < 256);
	process_fn = unmarshal_process_table[cc];

	unmarshal_trace(s, "process(%c -> %p)", cc, process_fn);
	if (process_fn == NULL) {
		PyErr_Format(PyExc_NotImplementedError, "%s: object type %c(0x%x) not implemented", __func__, cc, cc);
		return NULL;
	}

	return process_fn(s);
}

static ruby_instance_t *
unmarshal_process(unmarshal_state *s)
{
	unsigned int saved_indent = s->log.indent;
	bool saved_quiet = s->log.quiet;
	ruby_instance_t *result;

	s->log.indent += 2;
	result = __unmarshal_process(s);
	s->log.indent = saved_indent;
	s->log.quiet = saved_quiet;

	return result;
}

ruby_instance_t *
unmarshal_process_quiet(unmarshal_state *s)
{
	bool saved_quiet = s->log.quiet;
	ruby_instance_t *result;

	s->log.quiet = true;
	result = unmarshal_process(s);
	s->log.quiet = saved_quiet;

	return result;
}

static bool
unmarshal_check_signature(unmarshal_state *s, const unsigned char *sig, unsigned int sig_len)
{
	unsigned int i;

	for (i = 0; i < sig_len; ++i) {
		if (__ruby_reader_nextc(s->reader) != sig[i])
			return false;
	}

	return true;
}

bool
marshal48_check_signature(unmarshal_state *s)
{
	static unsigned char marshal48_sig[2] = {0x04, 0x08};

	return unmarshal_check_signature(s, marshal48_sig, sizeof(marshal48_sig));
}

ruby_instance_t *
marshal48_unmarshal_io(ruby_context_t *ruby, PyObject *io)
{
	unmarshal_state state;
	ruby_instance_t *result;

	printf("%s(%s)\n", __func__, py_stringify(io));
	unmarshal_state_init(&state, ruby, io);

	if (!marshal48_check_signature(&state)) {
		PyErr_SetString(PyExc_ValueError, "Data does not start with Marshal48 signature");
		return NULL;
	}

	unmarshal_trace(&state, "Unmarshaling data");
	result = unmarshal_process(&state);
	unmarshal_state_destroy(&state);

	return result;
}
