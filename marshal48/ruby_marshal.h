/*
Ruby Marshal48 implementation

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


#ifndef RUBY_MARSHAL_H
#define RUBY_MARSHAL_H

#include "ruby_trace.h"

/* anonymous decls for some structs */
struct ruby_io;
struct ruby_byteseq;

typedef struct ruby_unmarshal	ruby_unmarshal_t;

struct ruby_unmarshal {
	ruby_context_t *	ruby;
	struct ruby_io *	reader;

	ruby_trace_state_t *	tracing;
};

extern ruby_unmarshal_t *ruby_unmarshal_new(ruby_context_t *ctx, PyObject *io);
extern bool		ruby_unmarshal_next_fixnum(ruby_unmarshal_t *, long *);
extern const char *	ruby_unmarshal_next_string(ruby_unmarshal_t *marshal, const char *encoding);
extern bool		ruby_unmarshal_next_byteseq(ruby_unmarshal_t *s, struct ruby_byteseq *seq);
extern ruby_instance_t *ruby_unmarshal_next_instance(ruby_unmarshal_t *);
extern bool		ruby_unmarshal_object_instance_vars(ruby_unmarshal_t *s, ruby_instance_t *object);

typedef ruby_instance_t *(*ruby_object_factory_fn_t)(ruby_context_t *, const char *);
extern ruby_instance_t *ruby_unmarshal_object_instance(ruby_unmarshal_t *s, ruby_object_factory_fn_t factory);

#define ruby_unmarshal_trace(s, fmt ...) ruby_trace((s)->tracing, ##fmt)

#endif /* RUBY_MARSHAL_H */

