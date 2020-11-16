/*
Tracing functions

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

#include <assert.h>
#include <stdarg.h>
#include <Python.h>

#include "ruby_trace.h"

static ruby_trace_state_t *
__ruby_trace_new(ruby_trace_id_t id)
{
	ruby_trace_state_t *s;

	s = calloc(1, sizeof(*s));
	s->id = id;

	return s;
}

static void
__ruby_trace_free(ruby_trace_state_t *s)
{
	free(s);
}

ruby_trace_state_t *
ruby_trace_new(bool quiet)
{
	ruby_trace_state_t *s;

	s = __ruby_trace_new(1);
	s->quiet = quiet;
	return s;
}

void
ruby_trace_free(ruby_trace_state_t *s)
{
	assert(s->id == 1);
	__ruby_trace_free(s);
}

ruby_trace_id_t
ruby_trace_push(ruby_trace_state_t **tracep, bool quiet)
{
	ruby_trace_state_t *parent = *tracep;
	ruby_trace_state_t *child;

	child = __ruby_trace_new(parent->id + 1);
	child->indent += 2;
	child->quiet = child->quiet || quiet;

	*tracep = child;
	return parent->id;
}

void
ruby_trace_pop(ruby_trace_state_t **tracep, ruby_trace_id_t id)
{
	ruby_trace_state_t *child = *tracep;
	ruby_trace_state_t *parent;

	parent = child->parent;
	assert(parent != NULL);
	assert(parent->id == id);
	__ruby_trace_free(child);
	*tracep = parent;
}

void
__ruby_trace(ruby_trace_state_t *s, const char *fmt, ...)
{
	va_list ap;

	va_start(ap, fmt);
	fprintf(stderr, "%*.*s", s->indent, s->indent, "");
	vfprintf(stderr, fmt, ap);
	fputs("\n", stderr);
	va_end(ap);
}
