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


/*
 * String unmarshaling
 *
 * It would be nice if a string was just a string.
 * However, the string encoding is often transported as a string object
 * follwed by one instance variable E=True/False.
 * So we need a ruby.String object that understands the set_instance_var
 * protocol.
 */
static ruby_instance_t *
ruby_String_unmarshal(ruby_marshal_t *marshal)
{
	const char *raw_string;
	ruby_instance_t *string = NULL;

	if (!(raw_string = ruby_unmarshal_next_string(marshal, "latin1")))
		return NULL;

	ruby_marshal_trace(marshal, "decoded string \"%s\"", raw_string);

	string = ruby_String_new(marshal->ruby, raw_string);
	if (string == NULL)
		return NULL;

	return string;
}

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
ruby_String_to_python(ruby_String *self, ruby_converter_t *converter)
{
	if (self->str_value == NULL) {
		Py_RETURN_NONE;
	}
	return PyUnicode_FromString(self->str_value);
}

static bool
ruby_String_from_python(ruby_String *self, PyObject *py_obj, ruby_converter_t *converter)
{
        const char *value;

        if ((value = PyUnicode_AsUTF8(py_obj)) == NULL) {
                PyErr_SetString(PyExc_TypeError, "object does not seem to be a string");
                return false;
        }

	assign_string(&self->str_value, value);
	return true;
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

ruby_type_t ruby_String_type = {
	.name		= "String",
	.size		= sizeof(ruby_String),
	.registration	= RUBY_REG_OBJECT,

	.unmarshal	= (ruby_instance_unmarshal_fn_t) ruby_String_unmarshal,
	.del		= (ruby_instance_del_fn_t) ruby_String_del,
	.repr		= (ruby_instance_repr_fn_t) ruby_String_repr,
	.set_var	= (ruby_instance_set_var_fn_t) ruby_String_set_var,
	.to_python	= (ruby_instance_to_python_fn_t) ruby_String_to_python,
	.from_python	= (ruby_instance_from_python_fn_t) ruby_String_from_python,
};

ruby_instance_t *
ruby_String_new(ruby_context_t *ctx, const char *name)
{
	ruby_String *self;

	self = (ruby_String *) __ruby_instance_new(ctx, &ruby_String_type);
	self->str_value = strdup(name);

	assert(self->str_base.reg.id >= 0 && self->str_base.reg.kind == RUBY_REG_OBJECT);

	return (ruby_instance_t *) self;
}

bool
ruby_String_check(const ruby_instance_t *self)
{
	return self->op == &ruby_String_type;
}

const char *
ruby_String_get_value(const ruby_instance_t *self)
{
	if (!ruby_String_check(self))
		return NULL;
	return ((ruby_String *) self)->str_value;
}
