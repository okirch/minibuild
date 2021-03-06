/*
Ruby types core for marshal48

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


#include "extension.h"
#include "ruby_impl.h"

/*
 * ruby context management
 */
struct ruby_context {
	ruby_array_t		symbols;
	ruby_array_t		objects;
	ruby_array_t		emphemerals;
};

ruby_context_t *
ruby_context_new(void)
{
	ruby_context_t *ctx;

	ctx = calloc(1, sizeof(*ctx));
	return ctx;
}

void
ruby_context_free(ruby_context_t *ctx)
{
	ruby_array_destroy(&ctx->symbols);
	ruby_array_destroy(&ctx->objects);
	ruby_array_destroy(&ctx->emphemerals);

	free(ctx);
}

ruby_instance_t *
ruby_context_get_symbol(ruby_context_t *ctx, unsigned int ref)
{
	return ruby_array_get(&ctx->symbols, ref);
}

ruby_instance_t *
ruby_context_get_object(ruby_context_t *ctx, unsigned int ref)
{
	return ruby_array_get(&ctx->objects, ref);
}

ruby_instance_t *
ruby_context_find_symbol(ruby_context_t *ctx, const char *value)
{
	unsigned int i;

	for (i = 0; i < ctx->symbols.count; ++i) {
		ruby_instance_t *sym = ctx->symbols.items[i];
		const char *sym_name;

		sym_name = ruby_Symbol_get_name(sym);
		if (sym_name && !strcmp(sym_name, value))
			return sym;
	}

	return NULL;
}

/*
 * Converter
 * For now, this is just a thin wrapper object containing nothing but
 * a callback to a python factory function
 */
ruby_converter_t *
ruby_converter_new(ruby_context_t *ctx, PyObject *factory)
{
	ruby_converter_t *converter = calloc(1, sizeof(*converter));

	converter->context = ctx;
	if (factory) {
		converter->factory = factory;
		Py_INCREF(factory);
	}

	return converter;
}

void
ruby_converter_free(ruby_converter_t *converter)
{
	drop_object(&converter->factory);
	free(converter);
}

/*
 * Generic instance functions
 */
bool
__ruby_instance_check_type(const ruby_instance_t *self, const ruby_type_t *type)
{
	const ruby_type_t *self_type = self->op;

	while (self_type) {
		if (self_type == type)
			return true;
		self_type = self_type->base_type;
	}
	return false;
}

static void
__ruby_instance_register(ruby_context_t *ctx, ruby_instance_t *instance)
{
	const ruby_type_t *type;
	int registration = RUBY_REG_EPHEMERAL;
	ruby_array_t *array;

	for (type = instance->op; type; type = type->base_type) {
		if (type->registration != RUBY_REG_EPHEMERAL) {
			if (registration != RUBY_REG_EPHEMERAL && registration != type->registration) {
				fprintf(stderr, "%s: conflicting registration types %d vs %d\n",
						instance->op->name,
						registration, type->registration);
				abort();
			}
			registration = type->registration;
		}
	}

	switch (registration) {
	case RUBY_REG_EPHEMERAL:
		array = &ctx->emphemerals;
		break;

	case RUBY_REG_SYMBOL:
		array = &ctx->symbols;
		break;

	case RUBY_REG_OBJECT:
		array = &ctx->objects;
		break;

	default:
		fprintf(stderr, "%s: unsupported registration type %d\n", instance->op->name, registration);
		abort();
	}

	instance->reg.kind = registration;
	instance->reg.id = array->count;
	ruby_array_append(array, instance);
}

ruby_instance_t *
__ruby_instance_new(ruby_context_t *ctx, const ruby_type_t *type)
{
	ruby_instance_t *instance;

	assert(type->size >= sizeof(*instance));
	instance = calloc(1, type->size);

	instance->op = type;
	instance->reg.kind = -1;
	instance->reg.id = -1;
	instance->marshal_id = -1;

	/* automatically register the instance */
	__ruby_instance_register(ctx, instance);
	assert(ctx);

	return instance;
}

void
__ruby_instance_del(ruby_instance_t *self)
{
	if (self->native)
		Py_DECREF(self->native);
	memset(self, 0, sizeof(*self));
	free(self);
}

PyObject *
ruby_instance_to_python(ruby_instance_t *self, ruby_converter_t *converter)
{
	if (self->native == RUBY_NATIVE_NO_CACHE)
		return self->op->to_python(self, converter);

	if (self->native == NULL) {
		self->native = self->op->to_python(self, converter);
		if (self->native == NULL)
			return NULL;
	}

	Py_INCREF(self->native);
	return self->native;
}

ruby_instance_t *
ruby_symbol_from_python(PyObject *self, ruby_converter_t *converter)
{
	ruby_instance_t *instance;
	const char *value;

	if ((value = PyUnicode_AsUTF8(self)) == NULL) {
		PyErr_SetString(PyExc_TypeError, "object does not seem to be a string");
		return NULL;
	}

	instance = ruby_context_find_symbol(converter->context, value);
	if (instance != NULL)
		return instance;

	instance = ruby_Symbol_new(converter->context, value);

	instance->native = self;
	Py_INCREF(self);

	return instance;
}

ruby_instance_t *
ruby_instance_from_python(PyObject *self, ruby_converter_t *converter)
{
	const ruby_type_t *type = NULL;
	ruby_instance_t *instance;

	// printf("%s(%s)\n", __func__, self->ob_type->tp_name);
	if (self == Py_True)
		return (ruby_instance_t *) &ruby_True;
	if (self == Py_False)
		return (ruby_instance_t *) &ruby_False;
	if (self == Py_None)
		return (ruby_instance_t *) &ruby_None;

	if (PyList_Check(self)) {
		type = &ruby_Array_type;
	} else if (PyLong_Check(self)) {
		type = &ruby_Int_type;
	} else if (PyUnicode_Check(self)) {
		type = &ruby_String_type;
	} else if (PyDict_Check(self)) {
		type = &ruby_Hash_type;
	} else if (PyObject_HasAttrString(self, "dump")) {
		type = &ruby_UserDefined_type;
	} else if (PyObject_HasAttrString(self, "marshal_dump")) {
		type = &ruby_UserMarshal_type;
	} else if (PyObject_IsInstance(self, (PyObject *) &PyBaseObject_Type)) {
		type = &ruby_GenericObject_type;
	}

	if (type->get_cached && (instance = type->get_cached(converter, self)) != NULL)
		return instance;

	if (type == NULL || type->from_python == NULL) {
		PyErr_Format(PyExc_TypeError, "Python type %s has no corresponding ruby type", self->ob_type->tp_name);
		return NULL;
	}

	// printf("Trying to convert to %s\n", type->name);
	instance = __ruby_instance_new(converter->context, type);
	if (instance == NULL) {
		PyErr_Format(PyExc_RuntimeError, "Unable to instantiate ruby %s", type->name);
		return NULL;
	}

	instance->native = self;
	Py_INCREF(self);

	if (!type->from_python(instance, self, converter)) {
		if (!PyErr_Occurred())
			PyErr_Format(PyExc_RuntimeError, "Python conversion failed for ruby %s", type->name);
		return NULL;
	}

	if (type->add_cache)
		type->add_cache(instance, converter);

	return instance;
}

char *
ruby_instance_as_string(ruby_instance_t *self)
{
	const char *s = NULL;

	if (ruby_String_check(self)) {
		s = ruby_String_get_value(self);
	} else
	if (ruby_Symbol_check(self)) {
		s = ruby_Symbol_get_name(self);
	} else {
		fprintf(stderr, "Cannot get string value from %s object\n", self->op->name);
		return NULL;
	}

	if (s == NULL)
		s = "";

	return strdup(s);
}

/*
 * Booleans
 */
static const char *
ruby_Bool_repr(ruby_instance_t *instance, ruby_repr_context_t *ctx)
{
	if (instance == &ruby_True)
		return "True";
	if (instance == &ruby_False)
		return "False";

	return "AlienBool";
}

static PyObject *
ruby_Bool_to_python(ruby_instance_t *instance, ruby_converter_t *converter)
{
	if (instance == &ruby_True)
		Py_RETURN_TRUE;
	if (instance == &ruby_False)
		Py_RETURN_FALSE;

	PyErr_SetString(PyExc_ValueError, "Unknown Bool instance; cannot convert");
	return NULL;
}

static ruby_type_t ruby_Bool_methods = {
	.name		= "Bool",
	.size		= sizeof(ruby_instance_t),

	.del		= NULL,
	.repr		= ruby_Bool_repr,
	.to_python	= ruby_Bool_to_python,
};

const ruby_instance_t ruby_True = {
	.op		= &ruby_Bool_methods,
	.reg = {
		.id	= -1,
	},
	.native		= RUBY_NATIVE_NO_CACHE,
};

const ruby_instance_t ruby_False = {
	.op		= &ruby_Bool_methods,
	.reg = {
		.id	= -1,
	},
	.native		= RUBY_NATIVE_NO_CACHE,
};

bool
ruby_Bool_check(const ruby_instance_t *self)
{
	/* You cannot subclass Bool */
	return self->op == &ruby_Bool_methods;
}

bool
ruby_Bool_is_true(const ruby_instance_t *self)
{
	return self == &ruby_True;
}

bool
ruby_Bool_is_false(const ruby_instance_t *self)
{
	return self == &ruby_False;
}

/*
 * None
 */
static const char *
ruby_None_repr(ruby_instance_t *instance, ruby_repr_context_t *ctx)
{
	return "None";
}

static PyObject *
ruby_None_to_python(ruby_instance_t *instance, ruby_converter_t *converter)
{
	Py_RETURN_NONE;
}

static ruby_type_t ruby_None_methods = {
	.name		= "None",
	.size		= sizeof(ruby_instance_t),

	.del		= NULL,
	.repr		= ruby_None_repr,
	.to_python	= ruby_None_to_python,
};

const ruby_instance_t ruby_None = {
	.op		= &ruby_None_methods,
	.reg = {
		.id	= -1,
	},
	.native		= RUBY_NATIVE_NO_CACHE,
};

bool
ruby_None_check(const ruby_instance_t *self)
{
	/* You cannot subclass None */
	return self->op == &ruby_None_methods;
}
