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


typedef ruby_instance_t *(*ruby_object_factory_fn_t)(ruby_context_t *, const char *);

/*
 * Generic object, which is constructed as Classname + instance variables
 */
static ruby_instance_t *
ruby_GenericObject_unmarshal(ruby_unmarshal_t *marshal)
{
	ruby_instance_t *object;

	/* Create the object instance */
	object = ruby_unmarshal_object_instance(marshal, ruby_GenericObject_new);
	if (object == NULL)
		return NULL;

	/* Apply instance variables that follow */
	if (!ruby_unmarshal_object_instance_vars(marshal, object))
		return NULL;

	return object;
}


static void
ruby_GenericObject_del(ruby_GenericObject *self)
{
	drop_string(&self->obj_classname);
	ruby_dict_zap(&self->obj_vars);
	__ruby_instance_del((ruby_instance_t *) self);
}

static const char *
ruby_GenericObject_repr(ruby_GenericObject *self, ruby_repr_context_t *ctx)
{
	ruby_repr_buf *rbuf;

	rbuf = __ruby_repr_begin(ctx, 128);
	__ruby_repr_appendf(rbuf, "%s()", self->obj_classname);

	if (self->obj_vars.dict_keys.count != 0) {
		__ruby_repr_appendf(rbuf, "; ");
		if (!__ruby_dict_repr(&self->obj_vars, ctx, rbuf))
			return __ruby_repr_abort(rbuf);
	}
	return __ruby_repr_finish(rbuf);
}

bool
ruby_GenericObject_set_var(ruby_GenericObject *self, ruby_instance_t *key, ruby_instance_t *value)
{
	/* We don't strip @ off the attribute name; this happens later in __ruby_dict_convert. */
	ruby_dict_add(&self->obj_vars, key, value);
	return true;
}

/*
 * Convert from ruby type to native python type
 */
static bool
__ruby_object_setattr(PyObject *result, PyObject *attr_name, PyObject *attr_value)
{
	return PyObject_SetAttr(result, attr_name, attr_value) >= 0;
}

bool
__ruby_GenericObject_apply_vars(ruby_instance_t *self, PyObject *result, ruby_converter_t *converter)
{
	ruby_GenericObject *obj_self;

	if (!ruby_GenericObject_check(self)) {
		fprintf(stderr, "%s: object is not a GenericObject\n", __func__);
		return false;
	}

	obj_self = (ruby_GenericObject *) self;
	return __ruby_dict_convert(&obj_self->obj_vars, result, __ruby_object_setattr, converter);
}

static PyObject *
ruby_GenericObject_convert(ruby_GenericObject *self, ruby_converter_t *converter)
{
	PyObject *result;

	/* Look up classname in ruby module and instantiate */
	result = marshal48_instantiate_ruby_type(self->obj_classname, converter);
	if (result == NULL)
		return NULL;

	if (!__ruby_GenericObject_apply_vars(&self->obj_base, result, converter)) {
		/* FIXME: raise exception */
		Py_DECREF(result);
		return NULL;
	}

	return result;
}

ruby_type_t ruby_GenericObject_type = {
	.name		= "GenericObject",
	.size		= sizeof(ruby_GenericObject),
	.registration	= RUBY_REG_OBJECT,

	.unmarshal	= (ruby_instance_unmarshal_fn_t) ruby_GenericObject_unmarshal,
	.del		= (ruby_instance_del_fn_t) ruby_GenericObject_del,
	.repr		= (ruby_instance_repr_fn_t) ruby_GenericObject_repr,
	.set_var	= (ruby_instance_set_var_fn_t) ruby_GenericObject_set_var,
	.convert	= (ruby_instance_convert_fn_t) ruby_GenericObject_convert,
};

ruby_instance_t *
__ruby_GenericObject_new(ruby_context_t *ctx, const char *classname, const ruby_type_t *type)
{
	ruby_GenericObject *self;

	self = (ruby_GenericObject *) __ruby_instance_new(ctx, type);
	self->obj_classname = strdup(classname);
	ruby_dict_init(&self->obj_vars);

	return (ruby_instance_t *) self;
}

ruby_instance_t *
ruby_GenericObject_new(ruby_context_t *ctx, const char *classname)
{
	return __ruby_GenericObject_new(ctx, classname, &ruby_GenericObject_type);
}

bool
ruby_GenericObject_check(const ruby_instance_t *self)
{
	return __ruby_instance_check_type(self, &ruby_GenericObject_type);
}
