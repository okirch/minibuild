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

/*
 * Marshaled object, which is constructed by instantiating Classname() and calling
 * marshal_load() with an unmarshaled ruby object
 */
static ruby_instance_t *
ruby_UserMarshal_unmarshal(ruby_unmarshal_t *marshal)
{
	ruby_instance_t *object, *data;

	object = ruby_unmarshal_object_instance(marshal, ruby_UserMarshal_new);
	if (object == NULL)
		return NULL;

	data = ruby_unmarshal_next_instance(marshal);
	if (data == NULL)
		return NULL;

	if (!ruby_UserMarshal_set_data(object, data))
		return NULL;

	return object;
}

static void
ruby_UserMarshal_del(ruby_UserMarshal *self)
{
	/* Do not destroy the data we're referencing */
	ruby_GenericObject_type.del((ruby_instance_t *) self);
}

static const char *
ruby_UserMarshal_repr(ruby_UserMarshal *self, ruby_repr_context_t *ctx)
{
	ruby_repr_buf *rbuf;
	const ruby_dict_t *vars;

	rbuf = __ruby_repr_begin(ctx, 128);
	__ruby_repr_appendf(rbuf, "%s(",
			self->marsh_base.obj_classname);
	if (self->marsh_data != NULL)
		__ruby_repr_append(rbuf, __ruby_instance_repr(self->marsh_data, ctx));
	else
		__ruby_repr_append(rbuf, "<NIL>");
	__ruby_repr_append(rbuf, ")");

	vars = &self->marsh_base.obj_vars;
	if (vars->dict_keys.count != 0) {
		__ruby_repr_appendf(rbuf, "; ");
		if (!__ruby_dict_repr(vars, ctx, rbuf))
			return __ruby_repr_abort(rbuf);
	}
	return __ruby_repr_finish(rbuf);
}

/*
 * Convert from ruby type to native python type
 */
static PyObject *
ruby_UserMarshal_to_python(ruby_UserMarshal *self, ruby_converter_t *converter)
{
	PyObject *result, *data, *r;

	/* Look up classname in ruby module and instantiate */
	result = marshal48_instantiate_ruby_type(self->marsh_base.obj_classname, converter);
	if (result == NULL) {
		fprintf(stderr, "UserMarshal: unable to instantiate class %s\n", self->marsh_base.obj_classname);
		PyErr_Format(PyExc_RuntimeError, "unable to instantiate class %s", self->marsh_base.obj_classname);
		return NULL;
	}

	if (self->marsh_data == NULL) {
		data = Py_None;
		Py_INCREF(data);
	} else {
		data = ruby_instance_to_python(self->marsh_data, converter);
		if (data == NULL)
			goto failed;
	}

	/* Call the marshal_load() method of the new instance and pass it the data object */
	r = PyObject_CallMethod(result, "marshal_load", "O", data);
	Py_DECREF(data);

	if (r == NULL) {
		fprintf(stderr, "UserMarshal: unable to unmarshal: %s.marshal_load() failed\n", self->marsh_base.obj_classname);
		// PyErr_Format(PyExc_RuntimeError, "%s.marshal_load() failed", self->marsh_base.obj_classname);
		goto failed;
	}
	Py_DECREF(r);

	if (!__ruby_GenericObject_apply_vars(&self->marsh_base.obj_base, result, converter)) {
		fprintf(stderr, "UserMarshal: %s: failed to apply instance vars\n", self->marsh_base.obj_classname);
		PyErr_Format(PyExc_RuntimeError, "%s: failed to apply instance vars", self->marsh_base.obj_classname);
		goto failed;
	}

	return result;

failed:
	Py_DECREF(result);
	return NULL;
}

static bool
ruby_UserMarshal_from_python(ruby_UserMarshal *self, PyObject *py_obj, ruby_converter_t *converter)
{
	PyObject *data;

	/* Call the marshal_dump() method of the new instance and pass it the data object */
	data = PyObject_CallMethod(py_obj, "marshal_dump", "");
	if (data == NULL) {
		fprintf(stderr, "UserMarshal: unable to marshal: %s.marshal_dump() failed\n", py_obj->ob_type->tp_name);
		return false;
	}

	self->marsh_data = ruby_instance_from_python(data, converter);
	Py_DECREF(data);

	if (self->marsh_data == NULL)
		return false;

	return true;
}

ruby_type_t ruby_UserMarshal_type = {
	.name		= "UserMarshal",
	.size		= sizeof(ruby_UserMarshal),
	.base_type	= &ruby_GenericObject_type,

	.unmarshal	= (ruby_instance_unmarshal_fn_t) ruby_UserMarshal_unmarshal,
	.del		= (ruby_instance_del_fn_t) ruby_UserMarshal_del,
	.repr		= (ruby_instance_repr_fn_t) ruby_UserMarshal_repr,
	.to_python	= (ruby_instance_to_python_fn_t) ruby_UserMarshal_to_python,
	.from_python	= (ruby_instance_from_python_fn_t) ruby_UserMarshal_from_python,
};

ruby_instance_t *
ruby_UserMarshal_new(ruby_context_t *ctx, const char *classname)
{
	ruby_UserMarshal *self;

	self = (ruby_UserMarshal *) __ruby_GenericObject_new(ctx, classname, &ruby_UserMarshal_type);
	self->marsh_data = NULL;

	return (ruby_instance_t *) self;
}

bool
ruby_UserMarshal_check(const ruby_instance_t *self)
{
	return __ruby_instance_check_type(self, &ruby_UserMarshal_type);
}

bool
ruby_UserMarshal_set_data(ruby_instance_t *self, ruby_instance_t *data)
{
	if (!ruby_UserMarshal_check(self))
		return false;

	((ruby_UserMarshal *) self)->marsh_data = data;
	return true;
}
