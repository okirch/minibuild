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


#include <Python.h>
#include <structmember.h>

#include "extension.h"
#include "ruby_impl.h"

typedef struct {
	ruby_instance_t	sym_base;
	char *		sym_name;
} ruby_Symbol;

/*
 * A symbol is a byte sequence; no character encoding.
 */
static ruby_instance_t *
ruby_Symbol_unmarshal(ruby_marshal_t *marshal)
{
	const char *string;

	string = ruby_unmarshal_next_string(marshal, "latin1");
	if (string == NULL)
		return NULL;

	return ruby_Symbol_new(marshal->ruby, string);
}

static void
ruby_Symbol_del(ruby_Symbol *self)
{
	drop_string(&self->sym_name);
	__ruby_instance_del((ruby_instance_t *) self);
}

static const char *
ruby_Symbol_repr(ruby_Symbol *self, ruby_repr_context_t *ctx)
{
	if (self->sym_name == NULL)
		return "<NUL>";

	return self->sym_name;
}

/*
 * Convert from ruby type to native python type
 */
static PyObject *
ruby_Symbol_to_python(ruby_Symbol *self, ruby_converter_t *converter)
{
	if (self->sym_name == NULL) {
		Py_RETURN_NONE;
	}
	return PyUnicode_FromString(self->sym_name);
}

static bool
ruby_Symbol_from_python(ruby_Symbol *self, PyObject *py_obj, ruby_converter_t *converter)
{
	/* This is handled in ruby_symbol_from_python() */
	return false;
}

ruby_type_t ruby_Symbol_type = {
	.name		= "Symbol",
	.size		= sizeof(ruby_Symbol),
	.registration	= RUBY_REG_SYMBOL,

	.unmarshal	= (ruby_instance_unmarshal_fn_t) ruby_Symbol_unmarshal,
	.del		= (ruby_instance_del_fn_t) ruby_Symbol_del,
	.repr		= (ruby_instance_repr_fn_t) ruby_Symbol_repr,
	.to_python	= (ruby_instance_to_python_fn_t) ruby_Symbol_to_python,
	.from_python	= (ruby_instance_from_python_fn_t) ruby_Symbol_from_python,
};

ruby_instance_t *
ruby_Symbol_new(ruby_context_t *ctx, const char *name)
{
	ruby_Symbol *sym;

	sym = (ruby_Symbol *) __ruby_instance_new(ctx, &ruby_Symbol_type);
	sym->sym_name = strdup(name);

	return (ruby_instance_t *) sym;
}

bool
ruby_Symbol_check(const ruby_instance_t *self)
{
	return self->op == &ruby_Symbol_type;
}

const char *
ruby_Symbol_get_name(const ruby_instance_t *self)
{
	if (!ruby_Symbol_check(self))
		return NULL;
	return ((ruby_Symbol *) self)->sym_name;
}
