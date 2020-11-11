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
	ruby_GenericObject marsh_base;
	ruby_instance_t *	marsh_data;
} ruby_UserMarshal;


static void
ruby_UserMarshal_del(ruby_UserMarshal *self)
{
	/* Do not destroy the data we're referencing */
	ruby_GenericObject_methods.del((ruby_instance_t *) self);
}

static const char *
ruby_UserMarshal_repr(ruby_UserMarshal *self)
{
	ruby_repr_buf *rbuf;
	const ruby_dict_t *vars;

	rbuf = __ruby_repr_begin(128);
	__ruby_repr_appendf(rbuf, "%s(",
			self->marsh_base.obj_classname);
	if (self->marsh_data != NULL)
		__ruby_repr_append(rbuf, ruby_instance_repr(self->marsh_data));
	else
		__ruby_repr_append(rbuf, "<NIL>");
	__ruby_repr_append(rbuf, ")");

	vars = &self->marsh_base.obj_vars;
	if (vars->dict_keys.count != 0) {
		__ruby_repr_appendf(rbuf, "; ");
		if (!__ruby_dict_repr(vars, rbuf))
			return __ruby_repr_abort(rbuf);
	}
	return __ruby_repr_finish(rbuf);
}

/*
 * Convert from ruby type to native python type
 */
static PyObject *
ruby_UserMarshal_convert(ruby_UserMarshal *self)
{
	PyObject *result, *data, *r;

	/* Look up classname in ruby module and instantiate */
	result = marshal48_instantiate_ruby_type(self->marsh_base.obj_classname);

	if (result == NULL)
		return NULL;

	if (self->marsh_data == NULL) {
		data = Py_None;
		Py_INCREF(data);
	} else {
		data = ruby_instance_convert(self->marsh_data);
		if (data == NULL)
			goto failed;
	}

	/* Call the load_marshal() method of the new instance and pass it the data object */
	r = PyObject_CallMethod(result, "load", "O", data);
	Py_DECREF(data);

	if (r == NULL)
		goto failed;
	Py_DECREF(r);

	if (!__ruby_GenericObject_apply_vars(&self->marsh_base.obj_base, result)) {
		/* FIXME: raise exception */
		goto failed;
	}

	return result;

failed:
	Py_DECREF(result);
	return NULL;
}

static ruby_type_t ruby_UserMarshal_methods = {
	.name		= "UserMarshal",
	.size		= sizeof(ruby_UserMarshal),
	.base_type	= &ruby_GenericObject_methods,

	.del		= (ruby_instance_del_fn_t) ruby_UserMarshal_del,
	.repr		= (ruby_instance_repr_fn_t) ruby_UserMarshal_repr,
	.convert	= (ruby_instance_convert_fn_t) ruby_UserMarshal_convert,
};

ruby_instance_t *
ruby_UserMarshal_new(ruby_context_t *ctx, const char *classname)
{
	ruby_UserMarshal *self;

	self = (ruby_UserMarshal *) __ruby_GenericObject_new(ctx, classname, &ruby_UserMarshal_methods);
	self->marsh_data = NULL;

	return (ruby_instance_t *) self;
}

bool
ruby_UserMarshal_check(const ruby_instance_t *self)
{
	return __ruby_instance_check_type(self, &ruby_UserMarshal_methods);
}

bool
ruby_UserMarshal_set_data(ruby_instance_t *self, ruby_instance_t *data)
{
	if (!ruby_UserMarshal_check(self))
		return false;

	((ruby_UserMarshal *) self)->marsh_data = data;
	return true;
}
