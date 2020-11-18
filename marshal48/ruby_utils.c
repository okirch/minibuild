/*
Ruby util types

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

#include <sys/resource.h>

/*
 * Array functions
 */
void
ruby_array_init(ruby_array_t *array)
{
	memset(array, 0, sizeof(*array));
}

static inline void
__ruby_array_ensure_tailroom(ruby_array_t *array)
{
	if (array->count >= array->size) {
		unsigned long new_size;

		if (array->size == 0)
			array->size = 2;
		else if (array->size < 8192)
			array->size *= 2;
		else
			array->size += 8192;

		new_size = array->size * sizeof(array->items[0]);
		if (array->items == NULL)
			array->items = malloc(new_size);
		else
			array->items = realloc(array->items, new_size);
	}
}

void
ruby_array_append(ruby_array_t *array, ruby_instance_t *item)
{
	__ruby_array_ensure_tailroom(array);
	array->items[array->count++] = item;
}

void
ruby_array_insert(ruby_array_t *array, unsigned int where, ruby_instance_t *item)
{
	if (where >= array->count) {
		ruby_array_append(array, item);
		return;
	}

	__ruby_array_ensure_tailroom(array);
	memmove(array->items + where + 1, array->items + where, (array->count - where) * sizeof(array->items[0]));

	array->items[where] = item;
	array->count += 1;
}

ruby_instance_t *
ruby_array_get(ruby_array_t *array, unsigned int index)
{
	if (index >= array->count)
		return NULL;
	return array->items[index];
}

void
ruby_array_zap(ruby_array_t *array)
{
	if (array->items)
		free(array->items);
	memset(array, 0, sizeof(*array));
}

void
ruby_array_destroy(ruby_array_t *array)
{
	unsigned int i;

	for (i = 0; i < array->count; ++i)
		ruby_instance_del(array->items[i]);
	ruby_array_zap(array);
}

/*
 * Dict functions
 */
void
ruby_dict_init(ruby_dict_t *dict)
{
	memset(dict, 0, sizeof(*dict));
}

void
ruby_dict_add(ruby_dict_t *dict, ruby_instance_t *key, ruby_instance_t *value)
{
	ruby_array_append(&dict->dict_keys, key);
	ruby_array_append(&dict->dict_values, value);
}

/*
 * This just zaps the dict, but does not destroy its dict members
 */
void
ruby_dict_zap(ruby_dict_t *dict)
{
	ruby_array_zap(&dict->dict_keys);
	ruby_array_zap(&dict->dict_values);
}

void
ruby_dict_destroy(ruby_dict_t *dict)
{
	ruby_array_destroy(&dict->dict_keys);
	ruby_array_destroy(&dict->dict_values);
}

/*
 * Byteseq functions
 */
void
ruby_byteseq_init(ruby_byteseq_t *seq)
{
	memset(seq, 0, sizeof(*seq));
}

void
ruby_byteseq_destroy(ruby_byteseq_t *seq)
{
	if (seq->data)
		free(seq->data);
	memset(seq, 0, sizeof(*seq));
}

bool
ruby_byteseq_is_empty(const ruby_byteseq_t *seq)
{
	return seq->count == 0;
}

void
ruby_byteseq_set(ruby_byteseq_t *seq, const void *data, unsigned int count)
{
	ruby_byteseq_destroy(seq);

	seq->data = malloc(count);
	memcpy(seq->data, data, count);
	seq->count = count;
}

void
ruby_byteseq_append(ruby_byteseq_t *seq, const void *data, unsigned int count)
{
	if (seq->count == 0) {
		ruby_byteseq_set(seq, data, count);
	} else {
		seq->data = realloc(seq->data, seq->count + count);
		memcpy(seq->data + seq->count, data, count);
		seq->count += count;
	}
}

bool
__ruby_byteseq_repr(const ruby_byteseq_t *seq, ruby_repr_buf *rbuf)
{
	static const unsigned int max_bytes = 32;
	unsigned int i;

	if (!__ruby_repr_append(rbuf, "<"))
		return false;

	for (i = 0; i < seq->count && i < max_bytes; ++i) {
		char hex[3];

		if (i > 0 && !__ruby_repr_append(rbuf, " "))
			break;

		snprintf(hex, sizeof(hex), "%02x", seq->data[i]);
		if (!__ruby_repr_append(rbuf, hex))
			break;
	}

	if (i < seq->count)
		__ruby_repr_append(rbuf, "...");

	return true;
}

unsigned long
__report_memory_rss(void)
{
	struct rusage ru;

	getrusage(RUSAGE_SELF, &ru);
	return ru.ru_maxrss;
}
