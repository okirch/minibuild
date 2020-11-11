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
ruby_Bool_convert(ruby_instance_t *instance)
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
	.convert	= ruby_Bool_convert,
};

const ruby_instance_t ruby_True = {
	.op		= &ruby_Bool_methods,
	.reg = {
		.id	= -1,
	},
};

const ruby_instance_t ruby_False = {
	.op		= &ruby_Bool_methods,
	.reg = {
		.id	= -1,
	},
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
ruby_None_convert(ruby_instance_t *instance)
{
	Py_RETURN_NONE;
}

static ruby_type_t ruby_None_methods = {
	.name		= "None",
	.size		= sizeof(ruby_instance_t),

	.del		= NULL,
	.repr		= ruby_None_repr,
	.convert	= ruby_None_convert,
};

const ruby_instance_t ruby_None = {
	.op		= &ruby_None_methods,
	.reg = {
		.id	= -1,
	},
};

bool
ruby_None_check(const ruby_instance_t *self)
{
	/* You cannot subclass None */
	return self->op == &ruby_None_methods;
}
