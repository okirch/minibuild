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

typedef struct ruby_repr_buf_s	ruby_repr_buf;

struct ruby_array {
	unsigned int		count;
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
extern ruby_instance_t *ruby_array_get(ruby_array_t *array, unsigned int index);
/* This just zaps the array, but does not destroy its array members */
extern void		ruby_array_zap(ruby_array_t *);
extern void		ruby_array_destroy(ruby_array_t *);

extern void		ruby_dict_init(ruby_dict_t *);
extern void		ruby_dict_add(ruby_dict_t *, ruby_instance_t *key, ruby_instance_t *value);
/* This just zaps the dict, but does not destroy its dict members */
extern void		ruby_dict_zap(ruby_dict_t *);
extern bool		__ruby_dict_repr(const ruby_dict_t *dict, ruby_repr_buf *rbuf);
extern bool		__ruby_dict_convert(const ruby_dict_t *dict,
				PyObject *target,
				bool (*apply_fn)(PyObject *target, PyObject *key, PyObject *value));

extern void		ruby_byteseq_init(ruby_byteseq_t *);
extern void		ruby_byteseq_destroy(ruby_byteseq_t *);
extern bool		ruby_byteseq_is_empty(const ruby_byteseq_t *);
extern void		ruby_byteseq_append(ruby_byteseq_t *, const void *, unsigned int);
extern void		ruby_byteseq_set(ruby_byteseq_t *, const void *, unsigned int);
extern bool		__ruby_byteseq_repr(const ruby_byteseq_t *, ruby_repr_buf *rbuf);

/*
 * Helper functions for repr machinery.
 */
extern const char *	__ruby_repr_printf(const char *fmt, ...);
extern ruby_repr_buf *	__ruby_repr_begin(unsigned int size);
extern void		__ruby_repr_reserve_tail(ruby_repr_buf *, unsigned int tail);
extern void		__ruby_repr_unreserve(ruby_repr_buf *);
extern bool		__ruby_repr_appendf(ruby_repr_buf *, const char *fmt, ...);
extern bool		__ruby_repr_append(ruby_repr_buf *, const char *value);
extern const char *	__ruby_repr_finish(ruby_repr_buf *);
extern const char *	__ruby_repr_abort(ruby_repr_buf *);


extern ruby_reader_t *	ruby_reader_new(PyObject *io);
extern void		ruby_reader_free(ruby_reader_t *reader);
extern int		ruby_reader_fillbuf(ruby_reader_t *reader);;
extern int		__ruby_reader_nextc(ruby_reader_t *reader);
extern bool		ruby_reader_nextc(ruby_reader_t *reader, int *cccp);
extern bool		ruby_reader_nextw(ruby_reader_t *reader, unsigned int count, long *resultp);
extern bool		ruby_reader_next_byteseq(ruby_reader_t *reader, unsigned int count, ruby_byteseq_t *seq);


#endif /* RUBY_UTILS_H */

