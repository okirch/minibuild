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
	ruby_instance_t *	(*process)(ruby_unmarshal_t *s);
} unmarshal_processor_t;

extern ruby_instance_t *ruby_unmarshal_next_instance_quiet(ruby_unmarshal_t *s);

void
__ruby_unmarshal_trace(ruby_unmarshal_t *s, const char *fmt, ...)
{
	va_list ap;

	va_start(ap, fmt);
	fprintf(stderr, "%*.*s", s->log.indent, s->log.indent, "");
	vfprintf(stderr, fmt, ap);
	fputs("\n", stderr);
	va_end(ap);
}

/*
 * Manage the state object
 */
ruby_unmarshal_t *
ruby_unmarshal_new(ruby_context_t *ruby, PyObject *io)
{
	ruby_unmarshal_t *marshal;

	marshal = calloc(1, sizeof(*marshal));
	marshal->ruby = ruby;
	marshal->reader = ruby_reader_new(io);

	return marshal;
}

void
ruby_unmarshal_free(ruby_unmarshal_t *marshal)
{
	/* We do not delete the ruby context; that is done by the caller */
	ruby_reader_free(marshal->reader);
}

bool
ruby_unmarshal_next_fixnum(ruby_unmarshal_t *s, long *fixnump)
{
	ruby_reader_t *reader = s->reader;
	int cc;

	if (!ruby_reader_nextc(reader, &cc))
		return false;

	// ruby_unmarshal_trace(s, "int0=0x%x", cc);

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

bool
ruby_unmarshal_next_byteseq(ruby_unmarshal_t *s, ruby_byteseq_t *seq)
{
	ruby_reader_t *reader = s->reader;
	long count;

	if (!ruby_unmarshal_next_fixnum(s, &count))
		return false;

	assert(seq->count == 0);
	return ruby_reader_next_byteseq(reader, count, seq);
}

const char *
ruby_unmarshal_next_string(ruby_unmarshal_t *marshal, const char *encoding)
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
ruby_None_unmarshal(ruby_unmarshal_t *s)
{
	return (ruby_instance_t *) &ruby_None;
}

RUBY_UNMARSHAL_PROCESSOR(None);

static ruby_instance_t *
ruby_True_unmarshal(ruby_unmarshal_t *s)
{
	return (ruby_instance_t *) &ruby_True;
}

RUBY_UNMARSHAL_PROCESSOR(True);

static ruby_instance_t *
ruby_False_unmarshal(ruby_unmarshal_t *s)
{
	return (ruby_instance_t *) &ruby_False;
}

RUBY_UNMARSHAL_PROCESSOR(False);

/*
 * Process a symbol reference
 */
static ruby_instance_t *
ruby_SymbolReference_unmarshal(ruby_unmarshal_t *s)
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

	ruby_unmarshal_trace(s, "Referenced dymbol #%ld: %s", ref, ruby_Symbol_get_name(symbol));
	return symbol;
}

RUBY_UNMARSHAL_PROCESSOR(SymbolReference);

/*
 * Process an object reference
 */
static ruby_instance_t *
ruby_ObjectReference_unmarshal(ruby_unmarshal_t *s)
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

	ruby_unmarshal_trace(s, "Referenced object #%ld: %s", ref, ruby_instance_repr(object));
	return object;
}

RUBY_UNMARSHAL_PROCESSOR(ObjectReference);

/*
 * Common helper to create object instances that specify a Classname
 */
ruby_instance_t *
ruby_unmarshal_object_instance(ruby_unmarshal_t *s,
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
ruby_unmarshal_object_instance_vars(ruby_unmarshal_t *s, ruby_instance_t *object)
{
	long i, count;

	if (!ruby_unmarshal_next_fixnum(s, &count))
		return false;

	ruby_unmarshal_trace(s, "%s is followed by %ld instance variables", object->op->name, count);

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
		ruby_unmarshal_trace(s, "  key=%s value=%s",
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
ruby_ObjectWithInstanceVars_unmarshal(ruby_unmarshal_t *s)
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
__ruby_unmarshal_next_instance(ruby_unmarshal_t *s)
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

	if (!ruby_reader_nextc(s->reader, &cc))
		return NULL;

	assert(0 <= cc && cc < 256);

	type = unmarshal_type_table[cc];
	if (type != NULL) {
		assert(type->unmarshal != NULL);

		ruby_unmarshal_trace(s, "process(%c -> %s)", cc, type->name);
		result = type->unmarshal(s);
	} else {
		processor = unmarshal_processor_table[cc];
		if (processor != NULL) {
			ruby_unmarshal_trace(s, "process(%c -> %s)", cc, processor->name);
			result = processor->process(s);
		}
	}

	if (result == NULL) {
		fprintf(stderr, "Don't know how to handle marshal type %c(0x%02x)\n", cc, cc);
		return NULL;
	}

	ruby_unmarshal_trace(s, "Returning %s: %s", result->op->name, ruby_instance_repr(result));

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

ruby_instance_t *
ruby_unmarshal_next_instance(ruby_unmarshal_t *s)
{
	unsigned int saved_indent = s->log.indent;
	bool saved_quiet = s->log.quiet;
	ruby_instance_t *result;

	s->log.indent += 2;
	result = __ruby_unmarshal_next_instance(s);
	s->log.indent = saved_indent;
	s->log.quiet = saved_quiet;

	return result;
}

ruby_instance_t *
ruby_unmarshal_next_instance_quiet(ruby_unmarshal_t *s)
{
	bool saved_quiet = s->log.quiet;
	ruby_instance_t *result;

	s->log.quiet = true;
	result = ruby_unmarshal_next_instance(s);
	s->log.quiet = saved_quiet;

	return result;
}

static bool
unmarshal_check_signature(ruby_unmarshal_t *s, const unsigned char *sig, unsigned int sig_len)
{
	unsigned int i;

	for (i = 0; i < sig_len; ++i) {
		if (__ruby_reader_nextc(s->reader) != sig[i])
			return false;
	}

	return true;
}

bool
marshal48_check_signature(ruby_unmarshal_t *s)
{
	static unsigned char marshal48_sig[2] = {0x04, 0x08};

	return unmarshal_check_signature(s, marshal48_sig, sizeof(marshal48_sig));
}

ruby_instance_t *
marshal48_unmarshal_io(ruby_context_t *ruby, PyObject *io, bool quiet)
{
	ruby_unmarshal_t *marshal = ruby_unmarshal_new(ruby, io);
	ruby_instance_t *result;

	/* enable debug messages? */
	marshal->log.quiet = quiet;

	if (!marshal48_check_signature(marshal)) {
		/* PyErr_SetString(PyExc_ValueError, "Data does not start with Marshal48 signature"); */
		ruby_unmarshal_free(marshal);
		return NULL;
	}

	ruby_unmarshal_trace(marshal, "Unmarshaling data");
	result = ruby_unmarshal_next_instance(marshal);

	ruby_unmarshal_free(marshal);

	return result;
}
