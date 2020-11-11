/*
Simple ruby types for marshal48

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


typedef struct {
	ruby_instance_t	str_base;
	char *		str_value;
} ruby_String;


static void
ruby_String_del(ruby_String *self)
{
	drop_string(&self->str_value);
	__ruby_instance_del((ruby_instance_t *) self);
}

static const char *
ruby_String_repr(ruby_String *self)
{
	if (self->str_value == NULL)
		return "<NUL>";

	return self->str_value;
}

/*
 * Convert from ruby type to native python type
 */
static PyObject *
ruby_String_convert(ruby_String *self)
{
	if (self->str_value == NULL) {
		Py_RETURN_NONE;
	}
	return PyUnicode_FromString(self->str_value);
}

static bool
ruby_String_set_var(ruby_String *self, ruby_instance_t *key, ruby_instance_t *value)
{
	const char *name;

	if (!ruby_Symbol_check(key)) {
		fprintf(stderr, "%s: key is not a symbol", __func__);
		return false;
	}
	name = ruby_Symbol_get_name(key);

	/* String encoding True/False - not quite sure what this means;
	 * so we'll ignore it for now. */
	if (!strcmp(name, "E")) {
		if (!ruby_Bool_check(value)) {
			fprintf(stderr, "%s: instance variable E must be a boolean", __func__);
			return false;
		}

		if (ruby_Bool_is_true(value)) {
			/* Do something */
		} else {
			/* Do something else */
		}
	} else {
		fprintf(stderr, "%s: unsupported instance variable %s", __func__, name);
		return false;
	}

	return true;
}

static ruby_type_t ruby_String_methods = {
	.name		= "String",
	.size		= sizeof(ruby_String),
	.registration	= RUBY_REG_OBJECT,

	.del		= (ruby_instance_del_fn_t) ruby_String_del,
	.repr		= (ruby_instance_repr_fn_t) ruby_String_repr,
	.set_var	= (ruby_instance_set_var_fn_t) ruby_String_set_var,
	.convert	= (ruby_instance_convert_fn_t) ruby_String_convert,
};

ruby_instance_t *
ruby_String_new(ruby_context_t *ctx, const char *name)
{
	ruby_String *self;

	self = (ruby_String *) __ruby_instance_new(ctx, &ruby_String_methods);
	self->str_value = strdup(name);

	assert(self->str_base.reg.id >= 0 && self->str_base.reg.kind == RUBY_REG_OBJECT);

	return (ruby_instance_t *) self;
}

bool
ruby_String_check(const ruby_instance_t *self)
{
	return self->op == &ruby_String_methods;
}

const char *
ruby_String_get_value(const ruby_instance_t *self)
{
	if (!ruby_String_check(self))
		return NULL;
	return ((ruby_String *) self)->str_value;
}
