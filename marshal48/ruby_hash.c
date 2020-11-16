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
	ruby_instance_t	hash_base;
	ruby_dict_t	hash_dict;
} ruby_Hash;


static ruby_instance_t *
ruby_Hash_unmarshal(ruby_unmarshal_t *marshal)
{
	ruby_instance_t *hash;
	long i, count;

	if (!ruby_unmarshal_next_fixnum(marshal, &count))
		return NULL;

	ruby_unmarshal_trace(marshal, "Decoding hash with %ld objects", count);

	hash = ruby_Hash_new(marshal->ruby);

	for (i = 0; i < count; ++i) {
		ruby_instance_t *key, *value;

		key = ruby_unmarshal_next_instance(marshal);
		if (key == NULL)
			return NULL;

		value = ruby_unmarshal_next_instance(marshal);
		if (value == NULL)
			return NULL;

		if (!ruby_Hash_add(hash, key, value))
			return NULL;
	}

	return hash;
}

static void
ruby_Hash_del(ruby_Hash *self)
{
	ruby_dict_zap(&self->hash_dict);
	__ruby_instance_del((ruby_instance_t *) self);
}

bool
__ruby_dict_repr(const ruby_dict_t *dict, ruby_repr_context_t *ctx, ruby_repr_buf *rbuf)
{
	const ruby_array_t *keys = &dict->dict_keys;
	const ruby_array_t *values = &dict->dict_values;
	unsigned int i;

	assert(keys->count == values->count);

	__ruby_repr_reserve_tail(rbuf, sizeof(", ...}"));

	__ruby_repr_append(rbuf, "{");
	for (i = 0; i < keys->count; ++i) {
		const char *key_rep, *value_rep;

		key_rep = __ruby_instance_repr(keys->items[i], ctx);
		if (key_rep == NULL)
			key_rep = "<BAD>";
		value_rep = __ruby_instance_repr(values->items[i], ctx);
		if (value_rep == NULL)
			value_rep = "<BAD>";

		if (i != 0 && !__ruby_repr_append(rbuf, ", "))
			break;

		if (!__ruby_repr_appendf(rbuf, "%s=%s", key_rep, value_rep))
			break;
	}

	__ruby_repr_unreserve(rbuf);
	if (i < keys->count)
		__ruby_repr_append(rbuf, "...");
	__ruby_repr_append(rbuf, "}");

	return __ruby_repr_finish(rbuf);
}

/*
 * Helper function for converting ruby instances that come with a dict
 */
bool
__ruby_dict_to_python(const ruby_dict_t *dict, PyObject *target,
		bool (*apply_fn)(PyObject *target, PyObject *key, PyObject *value),
		ruby_converter_t *converter)
{
	const ruby_array_t *keys = &dict->dict_keys;
	const ruby_array_t *values = &dict->dict_values;
	unsigned int i, len;
	bool okay = true;

	len = keys->count;

	for (i = 0; okay && i < len; ++i) {
		ruby_instance_t *ruby_key;
		PyObject *key = NULL, *value;

		/* If the key is an attribute starting with @, strip it off.
		 * We do this in order to be able to directly call
		 * Python's setattr() with the attribute name */
		ruby_key = keys->items[i];
		if (ruby_Symbol_check(ruby_key)) {
			const char *attr_name = ruby_Symbol_get_name(ruby_key);

			if (attr_name && attr_name[0] == '@')
				key = PyUnicode_FromString(attr_name + 1);
		}

		if (key == NULL)
			key = ruby_instance_to_python(ruby_key, converter);

		value = ruby_instance_to_python(values->items[i], converter);

		if (key == NULL)
			return false;
		if (value == NULL) {
			Py_DECREF(key);
			return false;
		}

		okay = apply_fn(target, key, value);
		if (!okay)
			fprintf(stderr, "failed to apply %s\n", ruby_instance_repr(keys->items[i]));

		Py_DECREF(key);
		Py_DECREF(value);
	}

	return okay;
}

static const char *
ruby_Hash_repr(ruby_Hash *self, ruby_repr_context_t *ctx)
{
	ruby_repr_buf *rbuf;

	rbuf = __ruby_repr_begin(ctx, 256);
	if (!__ruby_dict_repr(&self->hash_dict, ctx, rbuf))
		return __ruby_repr_abort(rbuf);

	return __ruby_repr_finish(rbuf);
}

/*
 * Convert ruby instance to native python type
 */
static bool
__ruby_Hash_apply_key_value(PyObject *result, PyObject *key, PyObject *value)
{
	PyDict_SetItem(result, key, value);
	return true;
}

static PyObject *
ruby_Hash_to_python(ruby_Hash *self, ruby_converter_t *converter)
{
	PyObject *result;

	result = PyDict_New();
	if (!__ruby_dict_to_python(&self->hash_dict, result, __ruby_Hash_apply_key_value, converter)) {
		Py_DECREF(result);
		return NULL;
	}

	return result;
}

static bool
ruby_Hash_from_python(ruby_Hash *self, PyObject *py_obj, ruby_converter_t *converter)
{
	return false; /* not yet */
}

ruby_type_t ruby_Hash_type = {
	.name		= "Hash",
	.size		= sizeof(ruby_Hash),
	.registration	= RUBY_REG_OBJECT,

	.unmarshal	= (ruby_instance_unmarshal_fn_t) ruby_Hash_unmarshal,
	.del		= (ruby_instance_del_fn_t) ruby_Hash_del,
	.repr		= (ruby_instance_repr_fn_t) ruby_Hash_repr,
	.to_python	= (ruby_instance_to_python_fn_t) ruby_Hash_to_python,
	.from_python	= (ruby_instance_from_python_fn_t) ruby_Hash_from_python,
};

ruby_instance_t *
ruby_Hash_new(ruby_context_t *ctx)
{
	ruby_Hash *self;

	self = (ruby_Hash *) __ruby_instance_new(ctx, &ruby_Hash_type);
	ruby_dict_init(&self->hash_dict);

	return (ruby_instance_t *) self;
}

bool
ruby_Hash_check(const ruby_instance_t *self)
{
	return self->op == &ruby_Hash_type;
}

bool
ruby_Hash_add(const ruby_instance_t *self, ruby_instance_t *key, ruby_instance_t *value)
{
	if (!ruby_Hash_check(self))
		return false;
	ruby_dict_add(&((ruby_Hash *) self)->hash_dict, key, value);
	return true;
}
