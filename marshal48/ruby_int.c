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
	ruby_instance_t	int_base;
	long		int_value;
} ruby_Int;

static ruby_instance_t *
ruby_Int_unmarshal(ruby_marshal_t *marshal)
{
	long value;

	if (!ruby_unmarshal_next_fixnum(marshal, &value))
		return NULL;

	return ruby_Int_new(marshal->ruby, value);
}

static void
ruby_Int_del(ruby_Int *self)
{
	__ruby_instance_del((ruby_instance_t *) self);
}

static const char *
ruby_Int_repr(ruby_Int *self, ruby_repr_context_t *ctx)
{
	return __ruby_repr_printf(ctx, "%ld", self->int_value);
}

static PyObject *
ruby_Int_to_python(ruby_Int *self, ruby_converter_t *converter)
{
	return PyLong_FromLong(self->int_value);
}

static bool
ruby_Int_from_python(ruby_Int *self, PyObject *py_obj, ruby_converter_t *converter)
{
	return false; /* not yet */
}

ruby_type_t ruby_Int_type = {
	.name		= "Int",
	.size		= sizeof(ruby_Int),

	.unmarshal	= (ruby_instance_unmarshal_fn_t) ruby_Int_unmarshal,
	.del		= (ruby_instance_del_fn_t) ruby_Int_del,
	.repr		= (ruby_instance_repr_fn_t) ruby_Int_repr,
	.to_python	= (ruby_instance_to_python_fn_t) ruby_Int_to_python,
	.from_python	= (ruby_instance_from_python_fn_t) ruby_Int_from_python,
};

ruby_instance_t *
ruby_Int_new(ruby_context_t *ctx, long value)
{
	ruby_Int *inst;

	inst = (ruby_Int *) __ruby_instance_new(ctx, &ruby_Int_type);
	inst->int_value = value;

	return (ruby_instance_t *) inst;
}

bool
ruby_Int_check(const ruby_instance_t *self)
{
	return self->op == &ruby_Int_type;
}

long
ruby_Int_get_value(const ruby_instance_t *self)
{
	if (!ruby_Int_check(self))
		return 0;
	return ((ruby_Int *) self)->int_value;
}
