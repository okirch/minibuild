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
#include "utils.h"


typedef struct unmarshal_state {
	PyObject *		io;

	simple_object_array_t	symbols;
	simple_object_array_t	objects;

	struct unmarshal_buffer {
		unsigned int	pos;
		unsigned int	count;
		unsigned char	_data[1024];

		void *		temp_linear;
	} buffer;

	struct {
		unsigned int	indent;
		bool		quiet;
	} log;
} unmarshal_state;

enum {
	MARSHAL_OKAY = 0,
	MARSHAL_EOF = -1,
	MARSHAL_ERROR = -2,
};


static PyObject *	unmarshal_process(unmarshal_state *s);
static PyObject *	unmarshal_process_quiet(unmarshal_state *s);
static PyObject *	unmarshal_raise_exception(int code);

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
unmarshal_state_init(unmarshal_state *s, PyObject *io)
{
	memset(s, 0, sizeof(*s));

	Py_INCREF(io);
	s->io = io;
}

static void
unmarshal_state_destroy(unmarshal_state *s)
{
	simple_object_array_destroy(&s->symbols);
	simple_object_array_destroy(&s->objects);

	drop_object(&s->io);
}

/*
 * Manage the buffer object
 */
void
unmarshal_buffer_init(struct unmarshal_buffer *bp)
{
	memset(bp, 0, sizeof(*bp));
}

void
unmarshal_buffer_clear(struct unmarshal_buffer *bp)
{
	bp->pos = bp->count = 0;
	memset(bp->_data, 0, sizeof(bp->_data));
}

char *
unmarshal_buffer_get_linear_buffer(struct unmarshal_buffer *bp, unsigned long count)
{
	if (bp->temp_linear) {
		free(bp->temp_linear);
		bp->temp_linear = NULL;
	}
	bp->temp_linear = calloc(1, count);
	return bp->temp_linear;
}

void
unmarshal_buffer_destroy(struct unmarshal_buffer *bp)
{
	if (bp->temp_linear) {
		free(bp->temp_linear);
		bp->temp_linear = NULL;
	}
	unmarshal_buffer_init(bp);
}

static int
unmarshal_fillbuf(unmarshal_state *s)
{
	struct unmarshal_buffer *bp = &s->buffer;
	PyObject *b;

	memset(bp, 0, sizeof(*bp));

	unmarshal_tp(s);

	b = PyObject_CallMethod(s->io, "read", "i", sizeof(bp->_data));
	if (b == NULL)
		return MARSHAL_ERROR;

	printf("TP %s:%d: b=%s\n", __func__, __LINE__, py_stringify(b));
	fflush(stdout);

	bp->pos = 0;
	if (PyBytes_Check(b)) {
		bp->count = PyBytes_GET_SIZE(b);

		assert(bp->count <= sizeof(bp->_data));
		memcpy(bp->_data, PyBytes_AS_STRING(b), bp->count);
	} else {
		bp->count = PyByteArray_GET_SIZE(b);

		assert(bp->count <= sizeof(bp->_data));
		memcpy(bp->_data, PyByteArray_AS_STRING(b), bp->count);
	}

	printf("TP %s:%d: now have %u bytes\n", __func__, __LINE__, bp->count);
	Py_DECREF(b);
	return MARSHAL_OKAY;
}

static int
__unmarshal_nextc(unmarshal_state *s)
{
	struct unmarshal_buffer *bp = &s->buffer;

	if (bp->pos >= bp->count) {
		if (unmarshal_fillbuf(s) < 0)
			return MARSHAL_ERROR;
		if (bp->count == 0)
			return MARSHAL_EOF;
	}

	unmarshal_trace(s, "%s: about to return \\%03o", __func__, bp->_data[bp->pos]);
	return bp->_data[bp->pos++];
}

static inline bool
unmarshal_nextc(unmarshal_state *s, int *cccp)
{
	*cccp = __unmarshal_nextc(s);
	if (*cccp < 0) {
		unmarshal_raise_exception(*cccp);
		return false;
	}

	return true;
}

static bool
unmarshal_nextw(unmarshal_state *s, unsigned int count, long *resultp)
{
	unsigned int shift = 0;

	*resultp = 0;

	/* little endian byte order */
	for (shift = 0; count; --count, shift += 8) {
		int cc;

		if (!unmarshal_nextc(s, &cc))
			return false;

		*resultp += (cc << shift);
	}

	return true;
}

static bool
unmarshal_next_fixnum(unmarshal_state *s, long *fixnump)
{
	int cc;

	if (!unmarshal_nextc(s, &cc))
		return false;

	unmarshal_trace(s, "int0=0x%x", cc);

	switch (cc) {
	case 0:
		*fixnump = 0;
		return true;
	
	case 1:
	case 2:
	case 3:
		return unmarshal_nextw(s, cc, fixnump);

	case 0xff:
		if (!unmarshal_nextc(s, &cc))
			return false;
		*fixnump = 1 - cc;
		return true;

	case 0xfe:
	case 0xfd:
	case 0xfc:
		PyErr_Format(PyExc_NotImplementedError, "%s: fixnum format 0x%x not yet implemented", __func__, cc);
		return false;

		if (!unmarshal_nextw(s, cc ^ 0xff, fixnump))
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

static const char *
__unmarshal_next_byteseq(unmarshal_state *s, unsigned long *sizep)
{
	struct unmarshal_buffer *bp = &s->buffer;
	char *linear;
	long count;

	if (!unmarshal_next_fixnum(s, &count))
		return NULL;

	if (count <= (bp->count - bp->pos)) {
		linear = (char *) bp->_data + bp->pos;
		bp->pos += count;
	} else {
		long spos = 0, copy;

		linear = unmarshal_buffer_get_linear_buffer(bp, count);
		while (spos <= count) {
			if (bp->pos >= bp->count) {
				int r;

				if ((r = unmarshal_fillbuf(s)) < 0) {
					unmarshal_raise_exception(r);
					return NULL;
				}
			}

			copy = bp->count - bp->pos;
			if (copy > count - spos)
				copy = count - spos;
			memcpy(linear + spos, bp->_data + bp->pos, copy);
			spos += copy;
		}
	}

	*sizep = count;
	return linear;
}

PyObject *
unmarshal_next_string(unmarshal_state *s, const char *encoding)
{
	const char *data;
	unsigned long count;

	data = __unmarshal_next_byteseq(s, &count);
	if (data == NULL)
		return NULL;

	return PyUnicode_Decode(data, count, encoding, NULL);
}

static PyObject *
unmarshal_next_byteseq(unmarshal_state *s)
{
	const char *data;
	unsigned long count;

	data = __unmarshal_next_byteseq(s, &count);
	if (data == NULL)
		return NULL;

	return PyByteArray_FromStringAndSize(data, count);
}

/*
 * Simple constants
 */
static PyObject *
unmarshal_process_none(unmarshal_state *s)
{
	Py_RETURN_NONE;
}

static PyObject *
unmarshal_process_true(unmarshal_state *s)
{
	Py_RETURN_TRUE;
}

static PyObject *
unmarshal_process_false(unmarshal_state *s)
{
	Py_RETURN_FALSE;
}

/*
 * Integers
 */
static PyObject *
unmarshal_process_int(unmarshal_state *s)
{
	long value;

	if (!(unmarshal_next_fixnum(s, &value)))
		return NULL;

	return PyLong_FromLong(value);
}

/*
 * Define symbol
 */
static PyObject *
unmarshal_define_symbol(unmarshal_state *s, PyObject *string)
{
	simple_object_array_append(&s->symbols, string);

	unmarshal_trace(s, "unmarshal_define_symbol(%s) = %d", PyUnicode_AsUTF8(string), s->symbols.count);
	return string;
}

/*
 * A symbol is a byte sequence; no character encoding.
 */
static PyObject *
unmarshal_process_symbol(unmarshal_state *s)
{
	PyObject *string;

	string = unmarshal_next_string(s, "latin1");
	if (string == NULL)
		return NULL;

	return unmarshal_define_symbol(s, string);
}

static PyObject *
unmarshal_process_symbol_reference(unmarshal_state *s)
{
	PyObject *symbol;
	long ref;

	if (!unmarshal_next_fixnum(s, &ref))
		return NULL;

	symbol = simple_object_array_get(&s->symbols, ref);
	if (symbol == NULL) {
		PyErr_SetString(PyExc_IOError, "Invalid symbol reference");
		return NULL;
	}

	unmarshal_trace(s, "%s(%d) = \"%s\"", __func__, ref, PyUnicode_AsUTF8(symbol));
	Py_INCREF(symbol);
	return symbol;
}

/*
 * Register an object
 */
static PyObject *
unmarshal_register_object(unmarshal_state *s, PyObject *object)
{
	simple_object_array_append(&s->objects, object);
	return object;
}

static PyObject *
unmarshal_process_object_reference(unmarshal_state *s)
{
	PyObject *object;
	long ref;

	if (!unmarshal_next_fixnum(s, &ref))
		return NULL;

	object = simple_object_array_get(&s->objects, ref);
	if (object == NULL) {
		PyErr_SetString(PyExc_IOError, "Invalid object reference");
		return NULL;
	}

	unmarshal_trace(s, "Referenced object #%ld: %s", ref, py_stringify(object));
	Py_INCREF(object);
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
static PyObject *
unmarshal_create_string(PyObject *value)
{
	return marshal48_instantiate_ruby_type_with_arg("String", value);
}

static PyObject *
unmarshal_process_string(unmarshal_state *s)
{
	PyObject *py_string, *string = NULL;

	if (!(py_string = unmarshal_next_string(s, "latin1")))
		return NULL;

	string = unmarshal_create_string(py_string);
	if (string == NULL)
		goto out;

	/* Register all objects as soon as they get created; this seems to
	 * reflect the order in which the ruby marshal48 code assigns
	 * object IDs */
	unmarshal_register_object(s, string);

out:
	Py_DECREF(py_string);
	return string;
}

/*
 * Array processing
 */
static PyObject *
unmarshal_create_array(void)
{
	return marshal48_instantiate_ruby_type("Array");
}

static PyObject *
unmarshal_process_array(unmarshal_state *s)
{
	PyObject *array;
	long i, count;

	if (!unmarshal_next_fixnum(s, &count))
		return NULL;

	unmarshal_trace(s, "Decoding array with %ld objects", count);

	array = unmarshal_create_array();
	if (array == NULL)
		return NULL;
	unmarshal_tp(s);

	/* Register all objects as soon as they get created; this seems to
	 * reflect the order in which the ruby marshal48 code assigns
	 * object IDs */
	unmarshal_register_object(s, array);

	for (i = 0; i < count; ++i) {
		PyObject *item, *r;

		item = unmarshal_process(s);
		if (item == NULL)
			goto failed;
		unmarshal_tp(s);

		r = PyObject_CallMethod(array, "append", "O", item);
		Py_DECREF(item);

		unmarshal_tp(s);
		if (r == NULL)
			goto failed;
		unmarshal_tp(s);
	}

	unmarshal_trace(s, "return %p", array);
	return array;

failed:
	Py_DECREF(array);
	return NULL;
}

/*
 * Hash processing
 */
static PyObject *
unmarshal_create_hash(void)
{
	return marshal48_instantiate_ruby_type("Hash");
}

static PyObject *
unmarshal_process_hash(unmarshal_state *s)
{
	PyObject *hash;
	long i, count;

	if (!unmarshal_next_fixnum(s, &count))
		return NULL;

	unmarshal_trace(s, "Decoding hash with %ld objects", count);

	hash = unmarshal_create_hash();

	/* Register all objects as soon as they get created; this seems to
	 * reflect the order in which the ruby marshal48 code assigns
	 * object IDs */
	unmarshal_register_object(s, hash);

	for (i = 0; i < count; ++i) {
		PyObject *key, *value, *r;

		key = unmarshal_process(s);
		if (key == NULL)
			goto failed;

		value = unmarshal_process(s);
		if (value == NULL) {
			Py_DECREF(key);
			goto failed;
		}

		r = PyObject_CallMethod(hash, "set", "OO", key, value);
		Py_DECREF(key);
		Py_DECREF(value);

		if (r == NULL)
			goto failed;
	}

	return hash;

failed:
	Py_DECREF(hash);
	return NULL;
}

/*
 * Common helper to create object instances that specify a Classname
 */
static inline PyObject *
__unmarshal_process_object_class_instance(unmarshal_state *s, const char *ruby_type_name)
{
	PyObject *classname, *object;

	if (!(classname = unmarshal_process(s)))
		return NULL;

	object = marshal48_instantiate_ruby_type_with_arg("GenericObject", classname);
	Py_DECREF(classname);

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
__unmarshal_process_instance_vars(unmarshal_state *s, PyObject *object)
{
	long i, count;

	unmarshal_enter(s);
	if (!unmarshal_next_fixnum(s, &count))
		return false;

	unmarshal_trace(s, "%ld instance variables follow", count);

	for (i = 0; i < count; ++i) {
		PyObject *key, *value, *r;

		key = unmarshal_process_quiet(s);
		if (key == NULL)
			return false;

		value = unmarshal_process_quiet(s);
		if (value == NULL) {
			Py_DECREF(key);
			return false;
		}

		unmarshal_trace(s, "key=%s value=%s", py_stringify(key), py_stringify(value));

		r = PyObject_CallMethod(object, "set_instance_var", "OO", key, value);
		Py_DECREF(key);
		Py_DECREF(value);

		if (r == NULL)
			return false;
		Py_DECREF(r);
	}

	return true;
}


/*
 * Arbitrary object, followed by a bunch of instance variables
 */
static PyObject *
unmarshal_process_object_with_instance_vars(unmarshal_state *s)
{
	PyObject *object;

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
static PyObject *
unmarshal_process_generic_object(unmarshal_state *s)
{
	PyObject *object;

	object = __unmarshal_process_object_class_instance(s, "GenericObject");
	if (object == NULL)
		return NULL;

	if (!__unmarshal_process_instance_vars(s, object)) {
		Py_DECREF(object);
		return NULL;
	}

	return object;
}

/*
 * Marshaled object, which is constructed by instantiating Classname() and calling
 * marshal_load() with an unmarshaled ruby object
 */
static PyObject *
unmarshal_process_user_marshal(unmarshal_state *s)
{
	PyObject *object, *data;

	object = __unmarshal_process_object_class_instance(s, "UserMarshal");
	if (object == NULL)
		goto failed;

	data = unmarshal_process(s);
	if (data == NULL)
		goto failed1;

	if (PyObject_SetAttrString(object, "data", data) < 0)
		goto failed2;

	return object;

failed2:
	Py_DECREF(data);
failed1:
	Py_DECREF(object);
failed:
	return NULL;
}

/*
 * User Defined object, which is constructed by instantiating Classname() and calling
 * load() with a byte sequence (which may or may not contain marshaled data).
 */
static PyObject *
unmarshal_process_user_defined(unmarshal_state *s)
{
	PyObject *object, *data;

	object = __unmarshal_process_object_class_instance(s, "UserDefined");
	if (object == NULL)
		goto failed;

	data = unmarshal_next_byteseq(s);
	if (data == NULL)
		goto failed1;

	if (PyObject_SetAttrString(object, "data", data) < 0)
		goto failed2;

	return object;

failed2:
	Py_DECREF(data);
failed1:
	Py_DECREF(object);
failed:
	return NULL;
}

static PyObject *
unmarshal_raise_exception(int code)
{
	switch (code) {
	case MARSHAL_ERROR:
		PyErr_SetString(PyExc_IOError, "error while reading from IO stream");
		break;
	case MARSHAL_EOF:
		PyErr_SetString(PyExc_IOError, "unexpected EOF while reading from IO stream");
		break;
	default:
		PyErr_SetString(PyExc_IOError, "unknown error");
	}

	return NULL;
}

static PyObject *
__unmarshal_process(unmarshal_state *s)
{
	typedef PyObject *(*unmarshal_process_fn_t)(unmarshal_state *s);
	static unmarshal_process_fn_t unmarshal_process_table[256] = {
		['T'] = unmarshal_process_true,
		['F'] = unmarshal_process_false,
		['0'] = unmarshal_process_none,

		['i'] = unmarshal_process_int,
		[':'] = unmarshal_process_symbol,
		[';'] = unmarshal_process_symbol_reference,
		['@'] = unmarshal_process_object_reference,

		/* The following are all objects that have an object id (and can this be referenced by ID) */
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

	if (!unmarshal_nextc(s, &cc))
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

static PyObject *
unmarshal_process(unmarshal_state *s)
{
	unsigned int saved_indent = s->log.indent;
	bool saved_quiet = s->log.quiet;
	PyObject *result;

	s->log.indent += 2;
	result = __unmarshal_process(s);
	s->log.indent = saved_indent;
	s->log.quiet = saved_quiet;

	return result;
}

static PyObject *
unmarshal_process_quiet(unmarshal_state *s)
{
	bool saved_quiet = s->log.quiet;
	PyObject *result;

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
		if (__unmarshal_nextc(s) != sig[i])
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

PyObject *
marshal48_unmarshal_io(PyObject *io)
{
	unmarshal_state state;
	PyObject *result;

	printf("%s(%s)\n", __func__, py_stringify(io));
	unmarshal_state_init(&state, io);

	if (!marshal48_check_signature(&state)) {
		PyErr_SetString(PyExc_ValueError, "Data does not start with Marshal48 signature");
		return NULL;
	}

	unmarshal_trace(&state, "Unmarshaling data");
	result = unmarshal_process(&state);
	unmarshal_state_destroy(&state);

	return result;
}
