/*
Ruby instancedict utility

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

#undef RUBY_ARRAY_BSEARCH_DEBUG

enum {
	RUBY_ID_BUCKET_TYPE_INTERNAL,
	RUBY_ID_BUCKET_TYPE_LEAF,
};

#define RUBY_ID_HASH_BITS	32
#define RUBY_ID_HASH_SHIFT	4
#define RUBY_ID_HASH_MASK	((1 << RUBY_ID_HASH_SHIFT) - 1)
#define RUBY_ID_INSTANCES_PER_BUCKET (1 << RUBY_ID_HASH_SHIFT)
#define RUBY_ID_CHILDREN_PER_BUCKET 16

typedef struct ruby_id_bucket	ruby_id_bucket_t;
struct ruby_id_bucket {
	int			type;
	unsigned int		shift;

	union {
		struct {
			unsigned int	count;
			ruby_id_bucket_t *children[RUBY_ID_INSTANCES_PER_BUCKET];
		} internal;
		struct {
			unsigned int	count;
			ruby_instance_t *items[RUBY_ID_CHILDREN_PER_BUCKET];
		} leaf;
	};
};

struct ruby_instancedict {
	ruby_id_bucket_t	root;

	const char *		(*keyfunc)(const ruby_instance_t *);
};

struct ruby_id_search_key {
	unsigned int		hash;
	long			value;
};

static void			ruby_instancedict_make_key(ruby_instancedict_t *, const char *, struct ruby_id_search_key *);
static ruby_id_bucket_t *	ruby_id_bucket_new(int type);
static ruby_id_bucket_t *	ruby_id_bucket_split(ruby_id_bucket_t *, unsigned int);
static void			ruby_id_bucket_insert(ruby_id_bucket_t *b, ruby_instance_t *item);
static ruby_instance_t *	__ruby_string_instancedict_lookup(ruby_instancedict_t *id, const struct ruby_id_search_key *search_key);


ruby_instancedict_t *
ruby_string_instancedict_new(const char *(*keyfunc)(const ruby_instance_t *))
{
	ruby_instancedict_t *id;

	id = calloc(1, sizeof(*id));
	id->root.type = RUBY_ID_BUCKET_TYPE_INTERNAL;
	id->keyfunc = keyfunc;

	return id;
}

void
ruby_instancedict_dump(ruby_instancedict_t *id)
{
	void __ruby_string_instancedict_dump(ruby_id_bucket_t *b, unsigned int index)
	{
		unsigned int indent = b->shift / RUBY_ID_HASH_SHIFT;

		if (b->type == RUBY_ID_BUCKET_TYPE_LEAF) {
			printf("%*.*s%08x %p leaf with %u items\n",
					indent, indent, "",
					index,
					b, b->leaf.count);
		} else {
			unsigned int i;

			printf("%*.*s%08x %p internal\n",
					indent, indent, "",
					index, b);
			for (i = 0; i < RUBY_ID_INSTANCES_PER_BUCKET; ++i) {
				ruby_id_bucket_t *child = b->internal.children[i];

				if (child != NULL)
					__ruby_string_instancedict_dump(child, index | (i << b->shift));
			}
		}
	}
	__ruby_string_instancedict_dump(&id->root, 0);
	fflush(stdout);

}

void
ruby_instancedict_stats(ruby_instancedict_t *id, unsigned int *avg_depth, unsigned int *avg_leaf_size)
{
	unsigned long leaf_count = 0, leaf_depth = 0, leaf_size = 0;

	void __ruby_instancedict_stats(ruby_id_bucket_t *b)
	{
		unsigned int depth = b->shift / RUBY_ID_HASH_SHIFT;

		if (b->type == RUBY_ID_BUCKET_TYPE_LEAF) {
			leaf_depth += depth;
			leaf_size  += b->leaf.count;
			leaf_count += 1;
		} else {
			unsigned int i;

			for (i = 0; i < RUBY_ID_INSTANCES_PER_BUCKET; ++i) {
				ruby_id_bucket_t *child = b->internal.children[i];

				if (child != NULL)
					__ruby_instancedict_stats(child);
			}
		}
	}
	__ruby_instancedict_stats(&id->root);

	if (leaf_count == 0) {
		*avg_depth = *avg_leaf_size = 0;
	} else {
		*avg_depth = leaf_depth / leaf_count;
		*avg_leaf_size = leaf_size / leaf_count;
	}
}

static ruby_id_bucket_t *
__ruby_instancedict_find_leaf(ruby_id_bucket_t *b, unsigned int search_hash, bool create)
{
	while (b->type == RUBY_ID_BUCKET_TYPE_INTERNAL) {
		unsigned int index = (search_hash >> b->shift) & RUBY_ID_HASH_MASK;
		ruby_id_bucket_t *child;

		child = b->internal.children[index];
		if (child == NULL) {
			if (!create)
				return NULL;

			child = ruby_id_bucket_new(RUBY_ID_BUCKET_TYPE_LEAF);
			child->shift = b->shift + RUBY_ID_HASH_SHIFT;
			assert(child->shift < RUBY_ID_HASH_BITS);
			b->internal.children[index] = child;
		}
		b = child;
	}

	assert(b->type == RUBY_ID_BUCKET_TYPE_LEAF);
	return b;
}

static ruby_instance_t *
__ruby_string_instancedict_lookup_leaf(ruby_instancedict_t *id, ruby_id_bucket_t *b, const struct ruby_id_search_key *search_key)
{
	unsigned int i;

	for (i = 0; i < b->leaf.count; ++i) {
		ruby_instance_t *item = b->leaf.items[i];
		const char *item_value;

		item_value = id->keyfunc(item);
		if (item->hash_value == search_key->hash
		 && !strcmp(item_value, (const char *) search_key->value))
			return item;
	}

	return NULL;
}

static ruby_instance_t *
__ruby_string_instancedict_lookup(ruby_instancedict_t *id, const struct ruby_id_search_key *search_key)
{
	ruby_id_bucket_t *b;

	b = __ruby_instancedict_find_leaf(&id->root, search_key->hash, false);
	if (b == NULL)
		return NULL;

	return __ruby_string_instancedict_lookup_leaf(id, b, search_key);
}

ruby_instance_t *
ruby_string_instancedict_lookup(ruby_instancedict_t *id, const char *string)
{
	struct ruby_id_search_key search_key;

	ruby_instancedict_make_key(id, string, &search_key);
	return __ruby_string_instancedict_lookup(id, &search_key);
}

void
ruby_string_instancedict_insert(ruby_instancedict_t *id, ruby_instance_t *instance)
{
	struct ruby_id_search_key search_key;
	ruby_id_bucket_t *b;

	ruby_instancedict_make_key(id, id->keyfunc(instance), &search_key);
	b = __ruby_instancedict_find_leaf(&id->root, search_key.hash, true);

	while (b->leaf.count >= RUBY_ID_INSTANCES_PER_BUCKET)
		b = ruby_id_bucket_split(b, search_key.hash);

	instance->hash_value = search_key.hash;
	ruby_id_bucket_insert(b, instance);
}

static inline unsigned int
__djb2_hash(const char *str)
{
	unsigned long hash = 5381;
	int c;

	while ((c = *str++) != '\0')
		hash = ((hash << 5) + hash) + c; /* hash * 33 + c */

	return hash;
}


static void
ruby_instancedict_make_key(ruby_instancedict_t *id, const char *string, struct ruby_id_search_key *key)
{
	key->hash = __djb2_hash(string);
	key->value = (long) string;
}

static ruby_id_bucket_t *
ruby_id_bucket_new(int type)
{
	ruby_id_bucket_t *b;

	if (type == RUBY_ID_BUCKET_TYPE_LEAF)
		b = calloc(1, sizeof(*b) + RUBY_ID_INSTANCES_PER_BUCKET * sizeof(b->leaf.items[0]));
	else
		b = calloc(1, sizeof(*b));
	b->type = type;
	return b;
}

static inline void
ruby_id_bucket_free(ruby_id_bucket_t *b)
{
	free(b);
}

static void
ruby_id_bucket_insert(ruby_id_bucket_t *b, ruby_instance_t *item)
{
	assert(b->leaf.count < RUBY_ID_INSTANCES_PER_BUCKET);
	b->leaf.items[b->leaf.count++] = item;
}

static ruby_id_bucket_t *
ruby_id_bucket_split(ruby_id_bucket_t *b, unsigned int insert_hash)
{
	ruby_instance_t *instances[RUBY_ID_CHILDREN_PER_BUCKET];
	unsigned int i;

	assert(b->shift + RUBY_ID_HASH_SHIFT < RUBY_ID_HASH_BITS);

	assert(b->leaf.count == RUBY_ID_CHILDREN_PER_BUCKET);
	for (i = 0; i < RUBY_ID_CHILDREN_PER_BUCKET; ++i)
		instances[i] = b->leaf.items[i];

	b->type = RUBY_ID_BUCKET_TYPE_INTERNAL;
	memset(&b->internal, 0, sizeof(b->internal));

	for (i = 0; i < RUBY_ID_CHILDREN_PER_BUCKET; ++i) {
		ruby_instance_t *item = instances[i];
		ruby_id_bucket_t *child;

		child = __ruby_instancedict_find_leaf(b, item->hash_value, true);
		ruby_id_bucket_insert(child, item);
	}

	return __ruby_instancedict_find_leaf(b, insert_hash, true);
}
