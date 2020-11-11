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

static ruby_instance_t *
ruby_Array_unmarshal(ruby_unmarshal_t *marshal)
{
	ruby_instance_t *array;
	long i, count;

	if (!ruby_unmarshal_next_fixnum(marshal, &count))
		return NULL;

	ruby_unmarshal_trace(marshal, "Decoding array with %ld objects", count);

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
ruby_Array_repr(ruby_Array *self)
{
	ruby_repr_buf *rbuf;
	unsigned int i;

	if (self->arr_items.count == 0)
		return "[]";

	rbuf = __ruby_repr_begin(256);
	__ruby_repr_reserve_tail(rbuf, sizeof(", ...]"));

	__ruby_repr_append(rbuf, "[");
	for (i = 0; i < self->arr_items.count; ++i) {
		const char *item_rep;

		item_rep = ruby_instance_repr(self->arr_items.items[i]);
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
ruby_Array_convert(ruby_Array *self)
{
	PyObject *result;
	unsigned int i, len;

	len = self->arr_items.count;

	result = PyList_New(len);
	for (i = 0; i < len; ++i) {
		PyObject *item;

		item = ruby_instance_convert(self->arr_items.items[i]);

		/* FIXME: raise exception if conversion fails */
		assert(item);

		PyList_SET_ITEM(result, i, item);
	}

	return result;
}

ruby_type_t ruby_Array_type = {
	.name		= "Array",
	.size		= sizeof(ruby_Array),
	.registration	= RUBY_REG_OBJECT,

	.unmarshal	= (ruby_instance_unmarshal_fn_t) ruby_Array_unmarshal,
	.del		= (ruby_instance_del_fn_t) ruby_Array_del,
	.repr		= (ruby_instance_repr_fn_t) ruby_Array_repr,
	.convert	= (ruby_instance_convert_fn_t) ruby_Array_convert,
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
