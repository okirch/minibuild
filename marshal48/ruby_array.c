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
	ruby_instance_t	arr_base;
	ruby_array_t	arr_items;
} ruby_Array;

static bool
ruby_Array_marshal(ruby_Array *self, ruby_marshal_t *marshal)
{
	unsigned int i;

	if (!ruby_marshal_array_begin(marshal, self->arr_items.count, &self->arr_base.marshal_id))
		return false;

	for (i = 0; i < self->arr_items.count; ++i) {
		ruby_instance_t *item = self->arr_items.items[i];

		if (!ruby_marshal_next_instance(marshal, item))
			return false;
	}

	return true;
}

static ruby_instance_t *
ruby_Array_unmarshal(ruby_marshal_t *marshal)
{
	ruby_instance_t *array;
	long i, count;

	if (!ruby_unmarshal_next_fixnum(marshal, &count))
		return NULL;

	ruby_marshal_trace(marshal, "Decoding array with %ld objects", count);

	array = ruby_Array_new(marshal->ruby);
	if (array == NULL)
		return NULL;

	for (i = 0; i < count; ++i) {
		ruby_instance_t *item;

		item = ruby_unmarshal_next_instance(marshal);
		if (item == NULL)
			return NULL;

		if (!ruby_Array_append(array, item))
			return NULL;
	}

	return array;
}

static void
ruby_Array_del(ruby_Array *self)
{
	ruby_array_zap(&self->arr_items);
	__ruby_instance_del((ruby_instance_t *) self);
}

static const char *
ruby_Array_repr(ruby_Array *self, ruby_repr_context_t *ctx)
{
	ruby_repr_buf *rbuf;
	unsigned int i;

	if (self->arr_items.count == 0)
		return "[]";

	rbuf = __ruby_repr_begin(ctx, 256);
	__ruby_repr_reserve_tail(rbuf, sizeof(", ...]"));

	__ruby_repr_append(rbuf, "[");
	for (i = 0; i < self->arr_items.count; ++i) {
		const char *item_rep;

		item_rep = __ruby_instance_repr(self->arr_items.items[i], ctx);
		if (item_rep == NULL)
			item_rep = "<BAD>";

		if (i != 0 && !__ruby_repr_append(rbuf, ", "))
			break;

		if (!__ruby_repr_append(rbuf, item_rep))
			break;
	}

	__ruby_repr_unreserve(rbuf);
	if (i < self->arr_items.count)
		__ruby_repr_append(rbuf, "...");
	__ruby_repr_append(rbuf, "]");

	return __ruby_repr_finish(rbuf);
}

/*
 * Convert from ruby type to native python type
 */
static PyObject *
ruby_Array_to_python(ruby_Array *self, ruby_converter_t *converter)
{
	PyObject *result;
	unsigned int i, len;

	len = self->arr_items.count;

	result = PyList_New(len);
	for (i = 0; i < len; ++i) {
		ruby_instance_t *ruby_item = self->arr_items.items[i];
		PyObject *py_item;

		py_item = ruby_instance_to_python(ruby_item, converter);
		if (py_item == NULL) {
			fprintf(stderr, "Array item %u(%s): python conversion failed\n", i, ruby_item->op->name);
			fprintf(stderr, "  item=%s\n", ruby_instance_repr(ruby_item));
			// PyErr_Format(PyExc_RuntimeError, "Conversion of %s instance failed", ruby_item->op->name);
			goto failed;
		}

		PyList_SET_ITEM(result, i, py_item);
	}

	return result;

failed:
	Py_DECREF(result);
	return NULL;
}

static bool
ruby_Array_from_python(ruby_instance_t *self, PyObject *py_obj, ruby_converter_t *converter)
{
	unsigned int i, count;

	if (!PyList_Check(py_obj))
		return false;

	count = PyList_GET_SIZE(py_obj);
	for (i = 0; i < count; ++i) {
		ruby_instance_t *item;

		item = ruby_instance_from_python(PyList_GET_ITEM(py_obj, i), converter);
		if (item == NULL) {
			fprintf(stderr, "%s: list item %i converstion failed\n", __func__, i);
			return false;
		}

		if (!ruby_Array_append(self, item))
			return false;
	}

	return true;
}

ruby_type_t ruby_Array_type = {
	.name		= "Array",
	.size		= sizeof(ruby_Array),
	.registration	= RUBY_REG_OBJECT,

	.marshal	= (ruby_instance_marshal_fn_t) ruby_Array_marshal,
	.unmarshal	= (ruby_instance_unmarshal_fn_t) ruby_Array_unmarshal,
	.del		= (ruby_instance_del_fn_t) ruby_Array_del,
	.repr		= (ruby_instance_repr_fn_t) ruby_Array_repr,
	.to_python	= (ruby_instance_to_python_fn_t) ruby_Array_to_python,
	.from_python	= (ruby_instance_from_python_fn_t) ruby_Array_from_python,
};

ruby_instance_t *
ruby_Array_new(ruby_context_t *ruby)
{
	ruby_Array *self;

	self = (ruby_Array *) __ruby_instance_new(ruby, &ruby_Array_type);
	ruby_array_init(&self->arr_items);

	return (ruby_instance_t *) self;
}

bool
ruby_Array_check(const ruby_instance_t *self)
{
	return self->op == &ruby_Array_type;
}

bool
ruby_Array_append(const ruby_instance_t *self, ruby_instance_t *item)
{
	if (!ruby_Array_check(self))
		return false;
	ruby_array_append(&((ruby_Array *) self)->arr_items, item);
	return true;
}
