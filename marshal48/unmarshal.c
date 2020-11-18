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

#include "extension.h"
#include "ruby_utils.h"
#include "ruby_marshal.h"


typedef struct unmarshal_processor {
	const char *		name;
	ruby_instance_t *	(*process)(ruby_marshal_t *s);
} unmarshal_processor_t;

extern ruby_instance_t *ruby_unmarshal_next_instance_quiet(ruby_marshal_t *s);

/*
 * Manage the state object
 */
ruby_marshal_t *
ruby_unmarshal_new(ruby_context_t *ruby, PyObject *io)
{
	ruby_marshal_t *marshal;

	marshal = calloc(1, sizeof(*marshal));
	marshal->ruby = ruby;
	marshal->ioctx = ruby_io_new(io);

	marshal->next_obj_id = 0;
	marshal->next_sym_id = 0;

	return marshal;
}

void
ruby_unmarshal_flush(ruby_marshal_t *marshal)
{
	ruby_io_flushbuf(marshal->ioctx);
}

void
ruby_unmarshal_free(ruby_marshal_t *marshal)
{
	/* We do not delete the ruby context; that is done by the caller */
	ruby_io_free(marshal->ioctx);

	if (marshal->tracing)
		ruby_trace_free(marshal->tracing);
}

ruby_instance_t *
ruby_marshal_define_symbol(ruby_marshal_t *marshal, const char *value)
{
	ruby_context_t *ruby = marshal->ruby;
	ruby_instance_t *symbol;

	symbol = ruby_context_find_symbol(ruby, value);
	if (symbol == NULL)
		symbol = ruby_Symbol_new(ruby, value);

	return symbol;
}

/*
 * Representation of integers in ruby marshal48 is very compact, but
 * also somewhat bizarre.
 */
bool
ruby_unmarshal_next_fixnum(ruby_marshal_t *s, long *fixnump)
{
	ruby_io_t *reader = s->ioctx;
	int cc;

	if (!ruby_io_nextc(reader, &cc))
		return false;

	// ruby_marshal_trace(s, "int0=0x%x", cc);

	switch (cc) {
	case 0:
		*fixnump = 0;
		return true;
	
	case 1:
	case 2:
	case 3:
		return ruby_io_nextw(reader, cc, fixnump);

	case 0xff:
		if (!ruby_io_nextc(reader, &cc))
			return false;
		*fixnump = 1 - cc;
		return true;

	case 0xfe:
	case 0xfd:
	case 0xfc:
		PyErr_Format(PyExc_NotImplementedError, "%s: fixnum format 0x%x not yet implemented", __func__, cc);
		return false;

		if (!ruby_io_nextw(reader, cc ^ 0xff, fixnump))
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

bool
ruby_marshal_fixnum(ruby_marshal_t *s, long fixnum)
{
	ruby_io_t *writer = s->ioctx;
	long orig_value = fixnum;

	if (fixnum == 0)
		return ruby_io_putc(writer, '\0');

	if (fixnum >= 0) {
		unsigned char bytes[8];
		unsigned int i, len;

		if (fixnum < 0x80 - 5)
			return ruby_io_putc(writer, fixnum + 5);

		if (fixnum < 256)
			return ruby_io_putc(writer, 1)
			    && ruby_io_putc(writer, fixnum);

		for (len = 0; fixnum; fixnum >>= 8)
			bytes[len++] = fixnum & 0xff;

		if (len > 4) {
			fprintf(stderr, "value of %ld exceeds fixnum format\n", orig_value);
			return false;
		}

		if (!ruby_io_putc(writer, len))
			return false;

		for (i = 0; i < len; ++i)
			if (!ruby_io_putc(writer, bytes[i]))
				return false;

		return true;
	}

	fprintf(stderr, "Unable to represent fixnum %ld\n", orig_value);
	return false;
}

bool
ruby_unmarshal_next_byteseq(ruby_marshal_t *s, ruby_byteseq_t *seq)
{
	ruby_io_t *reader = s->ioctx;
	long count;

	if (!ruby_unmarshal_next_fixnum(s, &count))
		return false;

	assert(seq->count == 0);
	return ruby_io_next_byteseq(reader, count, seq);
}

const char *
ruby_unmarshal_next_string(ruby_marshal_t *marshal, const char *encoding)
{
	/* This is a static byteseq object, so we can return its internal
	 * data pointer and it will remain valid until the next call
	 * to this function. */
	static ruby_byteseq_t seq;

	/* zap what's left over from the previous call */
	ruby_byteseq_destroy(&seq);

	if (!ruby_unmarshal_next_byteseq(marshal, &seq))
		return NULL;

	/* NUL terminate */
	ruby_byteseq_append(&seq, "", 1);

	assert(!strcmp(encoding, "latin1"));
	return (const char *) seq.data;
	/* return PyUnicode_Decode(data, count, encoding, NULL); */
}

/*
 * Processors are a convenience - they combine a name (debug string) with a function ptr
 *
 * Note that most objects that we unmarshal have a type object that provides a .unmarshal
 * function. However, this is not possible for symbol/object references, or objects with
 * instance variables.
 */
#define RUBY_UNMARSHAL_PROCESSOR(NAME) \
static unmarshal_processor_t	ruby_##NAME##_processor = { \
	.name	= #NAME, \
	.process= ruby_##NAME##_unmarshal, \
}


/*
 * Simple constants
 */
static ruby_instance_t *
ruby_None_unmarshal(ruby_marshal_t *s)
{
	return (ruby_instance_t *) &ruby_None;
}

RUBY_UNMARSHAL_PROCESSOR(None);

static ruby_instance_t *
ruby_True_unmarshal(ruby_marshal_t *s)
{
	return (ruby_instance_t *) &ruby_True;
}

RUBY_UNMARSHAL_PROCESSOR(True);

static ruby_instance_t *
ruby_False_unmarshal(ruby_marshal_t *s)
{
	return (ruby_instance_t *) &ruby_False;
}

RUBY_UNMARSHAL_PROCESSOR(False);

/*
 * Process a symbol reference
 */
static ruby_instance_t *
ruby_SymbolReference_unmarshal(ruby_marshal_t *s)
{
	ruby_instance_t *symbol;
	long ref;

	if (!ruby_unmarshal_next_fixnum(s, &ref))
		return NULL;

	symbol = ruby_context_get_symbol(s->ruby, ref);
	if (symbol == NULL) {
		fprintf(stderr, "Invalid symbol reference %ld\n", ref);
		return NULL;
	}

	ruby_marshal_trace(s, "Referenced dymbol #%ld: %s", ref, ruby_Symbol_get_name(symbol));
	return symbol;
}

RUBY_UNMARSHAL_PROCESSOR(SymbolReference);

/*
 * Process an object reference
 */
static ruby_instance_t *
ruby_ObjectReference_unmarshal(ruby_marshal_t *s)
{
	ruby_instance_t *object;
	long ref;

	if (!ruby_unmarshal_next_fixnum(s, &ref))
		return NULL;

	object = ruby_context_get_object(s->ruby, ref);
	if (object == NULL) {
		fprintf(stderr, "Invalid object reference %ld\n", ref);
		return NULL;
	}

	ruby_marshal_trace(s, "Referenced object #%ld: %s", ref, ruby_instance_repr(object));
	return object;
}

RUBY_UNMARSHAL_PROCESSOR(ObjectReference);

/*
 * Common helper to create object instances that specify a Classname
 */
ruby_instance_t *
ruby_unmarshal_object_instance(ruby_marshal_t *s,
               ruby_instance_t * (*constructor)(ruby_context_t *, const char *))
{
	ruby_instance_t *name_instance, *object;
	char *classname;

	if (!(name_instance = ruby_unmarshal_next_instance(s)))
	       return NULL;

	classname = ruby_instance_as_string(name_instance);
	if (classname == NULL)
	       return NULL;

	object = constructor(s->ruby, classname);
	free(classname);

	return object;
}

/*
 * Common helper function to process instance variables
 */
bool
ruby_unmarshal_object_instance_vars(ruby_marshal_t *s, ruby_instance_t *object)
{
	long i, count;

	if (!ruby_unmarshal_next_fixnum(s, &count))
		return false;

	ruby_marshal_trace(s, "%s is followed by %ld instance variables", object->op->name, count);

	for (i = 0; i < count; ++i) {
		ruby_repr_context_t *repr_ctx;
		ruby_instance_t *key, *value;

		key = ruby_unmarshal_next_instance_quiet(s);
		if (key == NULL)
			return false;

		value = ruby_unmarshal_next_instance_quiet(s);
		if (value == NULL)
			return false;

		repr_ctx = ruby_repr_context_new();
		ruby_marshal_trace(s, "  key=%s value=%s",
					__ruby_instance_repr(key, repr_ctx),
					__ruby_instance_repr(value, repr_ctx));
		ruby_repr_context_free(repr_ctx);

		if (!ruby_instance_set_var(object, key, value))
			return false;
	}

	return true;
}


/*
 * Arbitrary object, followed by a bunch of instance variables
 */
static ruby_instance_t *
ruby_ObjectWithInstanceVars_unmarshal(ruby_marshal_t *s)
{
	ruby_instance_t *object;

	if (!(object = ruby_unmarshal_next_instance(s)))
		return NULL;

	/* Do not register the object here. If it *is* a proper object
	 * (rather than say a symbol or fixnum) it has already been
	 * registered inside the call to ruby_unmarshal_next_instance() above. */

	if (!ruby_unmarshal_object_instance_vars(s, object)) {
		Py_DECREF(object);
		return NULL;
	}

	return object;
}

RUBY_UNMARSHAL_PROCESSOR(ObjectWithInstanceVars);

static ruby_instance_t *
__ruby_unmarshal_next_instance(ruby_marshal_t *s)
{
	static const ruby_type_t *unmarshal_type_table[256] = {
		['i'] = &ruby_Int_type,
		[':'] = &ruby_Symbol_type,
		['"'] = &ruby_String_type,
		['['] = &ruby_Array_type,
		['{'] = &ruby_Hash_type,
		['o'] = &ruby_GenericObject_type,
		['u'] = &ruby_UserDefined_type,
		['U'] = &ruby_UserMarshal_type,
	};
	static unmarshal_processor_t *unmarshal_processor_table[256] = {
		['T'] = &ruby_True_processor,
		['F'] = &ruby_False_processor,
		['0'] = &ruby_None_processor,
		[';'] = &ruby_SymbolReference_processor,
		['@'] = &ruby_ObjectReference_processor,
		['I'] = &ruby_ObjectWithInstanceVars_processor,
	};
	const unmarshal_processor_t *processor;
	const ruby_type_t *type;
	ruby_instance_t *result = NULL;
	int cc;

	if (!ruby_io_nextc(s->ioctx, &cc))
		return NULL;

	assert(0 <= cc && cc < 256);

	type = unmarshal_type_table[cc];
	if (type != NULL) {
		assert(type->unmarshal != NULL);

		ruby_marshal_trace(s, "process(%c -> %s)", cc, type->name);
		result = type->unmarshal(s);
	} else {
		processor = unmarshal_processor_table[cc];
		if (processor != NULL) {
			ruby_marshal_trace(s, "process(%c -> %s)", cc, processor->name);
			result = processor->process(s);
		}
	}

	if (result == NULL) {
		fprintf(stderr, "Don't know how to handle marshal type %c(0x%02x)\n", cc, cc);
		return NULL;
	}

	ruby_marshal_trace(s, "Returning %s: %s", result->op->name, ruby_instance_repr(result));

	if (false) {
		static unsigned int num;

		if ((num % 100) == 0) {
			printf("%6u: RSS %lu kB\n", num, __report_memory_rss());
			fflush(stdout);
		}
		num += 1;
	}
	return result;
}

static ruby_instance_t *
__ruby_unmarshal_next_instance_logwrap(ruby_marshal_t *s, bool quiet)
{
	ruby_instance_t *result;
	ruby_trace_id_t saved_id;

	saved_id = ruby_trace_push(&s->tracing, quiet);
	result = __ruby_unmarshal_next_instance(s);
	ruby_trace_pop(&s->tracing, saved_id);

	return result;
}

ruby_instance_t *
ruby_unmarshal_next_instance(ruby_marshal_t *s)
{
	return __ruby_unmarshal_next_instance_logwrap(s, false);
}

ruby_instance_t *
ruby_unmarshal_next_instance_quiet(ruby_marshal_t *s)
{
	return __ruby_unmarshal_next_instance_logwrap(s, true);
}

bool
ruby_marshal_true(ruby_marshal_t *marshal)
{
	return ruby_io_putc(marshal->ioctx, 'T');
}

bool
ruby_marshal_false(ruby_marshal_t *marshal)
{
	return ruby_io_putc(marshal->ioctx, 'F');
}

bool
ruby_marshal_none(ruby_marshal_t *marshal)
{
	return ruby_io_putc(marshal->ioctx, '0');
}

bool
ruby_marshal_symbol_reference(ruby_marshal_t *marshal, unsigned int id)
{
	ruby_io_t *writer = marshal->ioctx;

	return ruby_io_putc(writer, ';') && ruby_marshal_fixnum(marshal, id);
}

bool
ruby_marshal_object_reference(ruby_marshal_t *marshal, unsigned int id)
{
	ruby_io_t *writer = marshal->ioctx;

	return ruby_io_putc(writer, '@') && ruby_marshal_fixnum(marshal, id);
}

/*
 * This function is different from the other ruby_marshal_ functions in
 * that its return value does not indicate an error.
 * true: we've seen this object before, I inserted a reference and the caller
 *	does not need to do anything.
 * false: new object, please marshal the object in its full glory.
 */
static bool
__ruby_marshal_maybe_object_reference(ruby_marshal_t *marshal, int *obj_id_ret)
{
	if (*obj_id_ret > 0)
		return ruby_marshal_object_reference(marshal, *obj_id_ret);

	*obj_id_ret = marshal->next_obj_id++;
	return false;
}

bool
ruby_marshal_bytes(ruby_marshal_t *marshal, const void *bytes, unsigned int count)
{
	ruby_io_t *writer = marshal->ioctx;

	return ruby_marshal_fixnum(marshal, count) && ruby_io_put_bytes(writer, bytes, count);
}

bool
ruby_marshal_symbol(ruby_marshal_t *marshal, const char *s, int *sym_id_ret)
{
	ruby_io_t *writer = marshal->ioctx;

	if (*sym_id_ret >= 0)
		return ruby_marshal_symbol_reference(marshal, *sym_id_ret);

	*sym_id_ret = marshal->next_sym_id++;
	return ruby_io_putc(writer, ':') && ruby_marshal_bytes(marshal, s, strlen(s));
}

bool
ruby_marshal_string(ruby_marshal_t *marshal, const char *s, int *obj_id_ret)
{
	static int e_sym_id = -1;
	ruby_io_t *writer = marshal->ioctx;

	/* If we've seen this object before, just insert a reference to it */
	if (__ruby_marshal_maybe_object_reference(marshal, obj_id_ret))
		return true;

	if (s == NULL || *s == '\0')
		return ruby_io_putc(writer, '"') && ruby_io_putc(writer, 0);

	if (!ruby_io_putc(writer, 'I')
	 || !ruby_io_putc(writer, '"')
         || !ruby_marshal_bytes(marshal, s, strlen(s)))
		return false;

	/* Followed by 1 instance variable E=True */
	if (!ruby_marshal_fixnum(marshal, 1))
                return false;

        if (!ruby_marshal_symbol(marshal, "E", &e_sym_id)
         || !ruby_marshal_true(marshal))
                return false;

	return true;
}

bool
ruby_marshal_array_begin(ruby_marshal_t *marshal, unsigned int count, int *obj_id_ret)
{
	ruby_io_t *writer = marshal->ioctx;

	/* If we've seen this object before, just insert a reference to it */
	if (__ruby_marshal_maybe_object_reference(marshal, obj_id_ret))
		return true;

	if (!ruby_io_putc(writer, '[')
	 || !ruby_marshal_fixnum(marshal, count))
		return false;

	return true;
}

bool
ruby_marshal_user_marshal_begin(ruby_marshal_t *marshal, const char *classname, int *obj_id_ret)
{
	ruby_io_t *writer = marshal->ioctx;
	ruby_instance_t *symbol;

	/* If we've seen this object before, just insert a reference to it */
	if (__ruby_marshal_maybe_object_reference(marshal, obj_id_ret))
		return true;

	symbol = ruby_marshal_define_symbol(marshal, classname);

	if (!ruby_io_putc(writer, 'U')
	 || !ruby_marshal_next_instance(marshal, symbol))
		return false;

	return true;
}

bool
ruby_marshal_next_instance(ruby_marshal_t *s, ruby_instance_t *instance)
{
	const ruby_type_t *type = instance->op;

	ruby_marshal_trace(s, "%s(%s = %s)", __func__, type->name, ruby_instance_repr(instance));

	if (type->marshal == NULL) {
		fprintf(stderr, "Don't know how to marshal a %s object (not implemented)\n", type->name);
		return false;
	}

	if (!type->marshal(instance, s)) {
		fprintf(stderr, "Failed to marshal %s object\n", type->name);
		return false;
	}

	return true;
}

static bool
unmarshal_check_signature(ruby_marshal_t *s, const unsigned char *sig, unsigned int sig_len)
{
	unsigned int i;

	for (i = 0; i < sig_len; ++i) {
		if (__ruby_io_nextc(s->ioctx) != sig[i])
			return false;
	}

	return true;
}

bool
marshal48_check_signature(ruby_marshal_t *s)
{
	static unsigned char marshal48_sig[2] = {0x04, 0x08};

	return unmarshal_check_signature(s, marshal48_sig, sizeof(marshal48_sig));
}

static bool
marshal_write_signature(ruby_marshal_t *s, const unsigned char *sig, unsigned int sig_len)
{
	unsigned int i;

	for (i = 0; i < sig_len; ++i) {
		if (!ruby_io_putc(s->ioctx, sig[i]))
			return false;
	}

	return true;
}

static bool
marshal48_write_signature(ruby_marshal_t *s)
{
	static unsigned char marshal48_sig[2] = {0x04, 0x08};

	return marshal_write_signature(s, marshal48_sig, sizeof(marshal48_sig));
}

ruby_instance_t *
marshal48_unmarshal_io(ruby_context_t *ruby, PyObject *io, bool quiet)
{
	ruby_marshal_t *marshal = ruby_unmarshal_new(ruby, io);
	ruby_instance_t *result;

	/* enable debug messages? */
	marshal->tracing = ruby_trace_new(quiet);

	if (!marshal48_check_signature(marshal)) {
		fprintf(stderr, "Data does not start with Marshal48 signature\n");
		ruby_unmarshal_free(marshal);
		return NULL;
	}

	ruby_marshal_trace(marshal, "Unmarshaling data");
	result = ruby_unmarshal_next_instance(marshal);

	ruby_unmarshal_free(marshal);

	return result;
}

bool
marshal48_marshal_io(ruby_context_t *ruby, ruby_instance_t *instance, PyObject *io, bool quiet)
{
	ruby_marshal_t *marshal = ruby_unmarshal_new(ruby, io);
	bool ok;

	marshal->tracing = ruby_trace_new(quiet);

	if (!marshal48_write_signature(marshal)) {
		fprintf(stderr, "Failed to write Marshal48 signature\n");
		ruby_unmarshal_free(marshal);
		return false;
	}

	ok = ruby_marshal_next_instance(marshal, instance);

	ruby_unmarshal_flush(marshal);
	ruby_unmarshal_free(marshal);
	return ok;
}
