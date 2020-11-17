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
	ruby_GenericObject udef_base;
	ruby_byteseq_t	udef_data;
} ruby_UserDefined;

static ruby_instance_t *
ruby_UserDefined_unmarshal(ruby_marshal_t *marshal)
{
	ruby_instance_t *object;
	ruby_byteseq_t *data;

	object = ruby_unmarshal_object_instance(marshal, ruby_UserDefined_new);
	if (object == NULL)
		return NULL;

	/* Get a pointer to the object's internal byteseq buffer */
	if (!(data = __ruby_UserDefined_get_data_rw(object))) {
		/* complain */
		return NULL;
	}

	/* Clear the byteseq object; read from stream */
	ruby_byteseq_destroy(data);
	if (!ruby_unmarshal_next_byteseq(marshal, data)) {
		/* complain */
		return NULL;
	}

	return object;
}


static void
ruby_UserDefined_del(ruby_UserDefined *self)
{
	ruby_byteseq_destroy(&self->udef_data);

	ruby_GenericObject_type.del((ruby_instance_t *) self);
}

static const char *
ruby_UserDefined_repr(ruby_UserDefined *self, ruby_repr_context_t *ctx)
{
	ruby_repr_buf *rbuf;
	const ruby_dict_t *vars;

	rbuf = __ruby_repr_begin(ctx, 128);
	__ruby_repr_appendf(rbuf, "%s(",
			self->udef_base.obj_classname);
	__ruby_byteseq_repr(&self->udef_data, rbuf);
	__ruby_repr_append(rbuf, ")");

	vars = &self->udef_base.obj_vars;
	if (vars->dict_keys.count != 0) {
		__ruby_repr_append(rbuf, "; ");
		if (!__ruby_dict_repr(vars, ctx, rbuf))
			return __ruby_repr_abort(rbuf);
	}
	return __ruby_repr_finish(rbuf);
}

/*
 * Convert from ruby type to native python type
 */
static PyObject *
ruby_UserDefined_to_python(ruby_UserDefined *self, ruby_converter_t *converter)
{
	const ruby_byteseq_t *bytes = &self->udef_data;
	PyObject *result, *data, *r;

	/* Look up classname in ruby module and instantiate */
	result = marshal48_instantiate_ruby_type(self->udef_base.obj_classname, converter);

	if (result == NULL) {
		fprintf(stderr, "UserDefined: unable to instantiate class %s\n", self->udef_base.obj_classname);
		PyErr_Format(PyExc_RuntimeError, "unable to instantiate class %s", self->udef_base.obj_classname);
		return NULL;
	}

	if (ruby_byteseq_is_empty(bytes)) {
		data = Py_None;
		Py_INCREF(data);
	} else {
		data = PyByteArray_FromStringAndSize((const char *) bytes->data, bytes->count);
		if (data == NULL)
			goto failed;
	}

	/* Call the load() method of the new instance and pass it the byteseq */
	r = PyObject_CallMethod(result, "load", "O", data);
	Py_DECREF(data);

	if (r == NULL) {
		fprintf(stderr, "UserDefined: unable to unmarshal: %s.load() failed\n", self->udef_base.obj_classname);
		PyErr_Format(PyExc_RuntimeError, "%s.load() failed", self->udef_base.obj_classname);
		goto failed;
	}
	Py_DECREF(r);

	if (!__ruby_GenericObject_apply_vars(&self->udef_base.obj_base, result, converter)) {
		/* FIXME: raise exception */
		goto failed;
	}

	return result;

failed:
	Py_DECREF(result);
	return NULL;
}

ruby_type_t ruby_UserDefined_type = {
	.name		= "UserDefined",
	.size		= sizeof(ruby_UserDefined),
	.base_type	= &ruby_GenericObject_type,

	.unmarshal	= (ruby_instance_unmarshal_fn_t) ruby_UserDefined_unmarshal,
	.del		= (ruby_instance_del_fn_t) ruby_UserDefined_del,
	.repr		= (ruby_instance_repr_fn_t) ruby_UserDefined_repr,
	.to_python	= (ruby_instance_to_python_fn_t) ruby_UserDefined_to_python,
};

ruby_instance_t *
ruby_UserDefined_new(ruby_context_t *ctx, const char *classname)
{
	ruby_UserDefined *self;

	self = (ruby_UserDefined *) __ruby_GenericObject_new(ctx, classname, &ruby_UserDefined_type);
	ruby_byteseq_init(&self->udef_data);

	return (ruby_instance_t *) self;
}

bool
ruby_UserDefined_check(const ruby_instance_t *self)
{
	return __ruby_instance_check_type(self, &ruby_UserDefined_type);
}

bool
ruby_UserDefined_set_data(ruby_instance_t *self, const void *data, unsigned int count)
{
	if (!ruby_UserDefined_check(self))
		return false;

	ruby_byteseq_set(&((ruby_UserDefined *) self)->udef_data, data, count);
	return true;
}

ruby_byteseq_t *
__ruby_UserDefined_get_data_rw(ruby_instance_t *self)
{
	if (!ruby_UserDefined_check(self))
		return NULL;

	return &((ruby_UserDefined *) self)->udef_data;
}
