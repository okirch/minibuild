/*
Ruby tracing

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


#ifndef RUBY_TRACE_H
#define RUBY_TRACE_H

#include <stdbool.h>

typedef unsigned int		ruby_trace_id_t;
typedef struct ruby_trace_state	ruby_trace_state_t;

struct ruby_trace_state {
	ruby_trace_id_t		id;
	ruby_trace_state_t *	parent;

	unsigned int		indent;
	bool			quiet;
};

extern ruby_trace_state_t *	ruby_trace_new(bool quiet);
extern void			ruby_trace_free(ruby_trace_state_t *);
extern ruby_trace_id_t		ruby_trace_push(ruby_trace_state_t **, bool quiet);
extern void			ruby_trace_pop(ruby_trace_state_t **, ruby_trace_id_t);

extern void			__ruby_trace(ruby_trace_state_t *s, const char *fmt, ...);


#define ruby_trace(s, fmt ...)  do {\
        if (!(s)->quiet) \
                __ruby_trace(s, ## fmt); \
} while (0)

#endif /* RUBY_TRACE_H */


