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


#ifndef RUBY_UTILS_H
#define RUBY_UTILS_H

#include "ruby_marshal.h"

typedef struct ruby_repr_buf_s	ruby_repr_buf;
typedef struct ruby_array	ruby_array_t;
typedef struct ruby_byteseq	ruby_byteseq_t;
typedef struct ruby_dict	ruby_dict_t;
typedef struct ruby_io		ruby_io_t;


struct ruby_array {
	unsigned int		count;
	unsigned int		size;
	ruby_instance_t **	items;
};

struct ruby_byteseq {
	unsigned int		count;
	unsigned char *		data;
};

struct ruby_dict {
	ruby_array_t		dict_keys;
	ruby_array_t		dict_values;
};

extern void		ruby_array_init(ruby_array_t *);
extern void		ruby_array_append(ruby_array_t *, ruby_instance_t *);
extern void		ruby_array_insert(ruby_array_t *, unsigned int, ruby_instance_t *);
extern ruby_instance_t *ruby_array_get(ruby_array_t *array, unsigned int index);
/* This just zaps the array, but does not destroy its array members */
extern void		ruby_array_zap(ruby_array_t *);
extern void		ruby_array_destroy(ruby_array_t *);


/*
 * instancedict lets you search for ruby instances
 */
typedef struct ruby_instancedict ruby_instancedict_t;

extern ruby_instancedict_t *ruby_string_instancedict_new(const char *(*keyfunc)(const ruby_instance_t *));
extern ruby_instance_t *ruby_string_instancedict_lookup(ruby_instancedict_t *, const char *);
extern void		ruby_string_instancedict_insert(ruby_instancedict_t *, ruby_instance_t *);
extern void		ruby_instancedict_dump(ruby_instancedict_t *);
extern void		ruby_instancedict_stats(ruby_instancedict_t *,
				unsigned int *avg_depth,
				unsigned int *avg_leaf_size);

extern void		ruby_dict_init(ruby_dict_t *);
extern void		ruby_dict_add(ruby_dict_t *, ruby_instance_t *key, ruby_instance_t *value);
/* This just zaps the dict, but does not destroy its dict members */
extern void		ruby_dict_zap(ruby_dict_t *);
extern bool		__ruby_dict_repr(const ruby_dict_t *dict, ruby_repr_context_t *, ruby_repr_buf *rbuf);
extern bool		__ruby_dict_to_python(const ruby_dict_t *dict,
				PyObject *target,
				bool (*apply_fn)(PyObject *target, PyObject *key, PyObject *value),
				ruby_converter_t *converter);

extern void		ruby_byteseq_init(ruby_byteseq_t *);
extern void		ruby_byteseq_destroy(ruby_byteseq_t *);
extern bool		ruby_byteseq_is_empty(const ruby_byteseq_t *);
extern void		ruby_byteseq_append(ruby_byteseq_t *, const void *, unsigned int);
extern void		ruby_byteseq_set(ruby_byteseq_t *, const void *, unsigned int);
extern bool		__ruby_byteseq_repr(const ruby_byteseq_t *, ruby_repr_buf *rbuf);

/*
 * Helper functions for repr machinery.
 */
extern ruby_repr_context_t *ruby_repr_context_new(void);
extern void		ruby_repr_context_free(ruby_repr_context_t *ctx);
extern const char *	__ruby_instance_repr(ruby_instance_t *, ruby_repr_context_t *);
extern const char *	__ruby_repr_printf(ruby_repr_context_t *, const char *fmt, ...);
extern ruby_repr_buf *	__ruby_repr_begin(ruby_repr_context_t *, unsigned int size);
extern void		__ruby_repr_reserve_tail(ruby_repr_buf *, unsigned int tail);
extern void		__ruby_repr_unreserve(ruby_repr_buf *);
extern bool		__ruby_repr_appendf(ruby_repr_buf *, const char *fmt, ...);
extern bool		__ruby_repr_append(ruby_repr_buf *, const char *value);
extern const char *	__ruby_repr_finish(ruby_repr_buf *);
extern const char *	__ruby_repr_abort(ruby_repr_buf *);


extern ruby_io_t *	ruby_io_new(PyObject *io);
extern void		ruby_io_free(ruby_io_t *reader);
extern int		ruby_io_fillbuf(ruby_io_t *reader);;
extern bool		ruby_io_flushbuf(ruby_io_t *reader);;
extern int		__ruby_io_nextc(ruby_io_t *reader);
extern bool		ruby_io_nextc(ruby_io_t *reader, int *cccp);
extern bool		ruby_io_nextw(ruby_io_t *reader, unsigned int count, long *resultp);
extern bool		ruby_io_next_byteseq(ruby_io_t *reader, unsigned int count, ruby_byteseq_t *seq);
extern bool		ruby_io_putc(ruby_io_t *reader, int);
extern bool		ruby_io_put_bytes(ruby_io_t *reader, const void *, unsigned int);

extern unsigned long	__report_memory_rss(void);

#endif /* RUBY_UTILS_H */

