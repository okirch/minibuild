/*
Ruby repr support

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

struct ruby_repr_context {
	struct ruby_repr_context *parent;
	ruby_repr_buf *	siblings;
	ruby_repr_buf *	children;
};

struct ruby_repr_buf_s {
	struct ruby_repr_context context;

	unsigned int	wpos, size, reserved;
	char		data[1];
};

static char		__parrot[4] = { 0xde, 0xad, 0xbe, 0xef }; /* this parrot is dead */

static struct ruby_repr_context ruby_repr_top_context;
static struct ruby_repr_context *ruby_repr_current_context = &ruby_repr_top_context;


static void		__ruby_repr_buf_free(ruby_repr_buf *rbuf);

static void
__ruby_repr_context_insert(struct ruby_repr_context *ctx, ruby_repr_buf *child)
{
	struct ruby_repr_context *child_ctx = &child->context;

	child_ctx->siblings = ctx->children;
	ctx->children = child;
	child_ctx->parent = ctx;
}

static inline ruby_repr_buf *
__ruby_repr_context_pop_child(struct ruby_repr_context *ctx)
{
	ruby_repr_buf *child;

	if ((child = ctx->children) != NULL) {
		ctx->children = child->context.siblings;
		child->context.parent = NULL;
	}

	return child;
}

static void
__ruby_repr_context_push(struct ruby_repr_context *ctx)
{
	assert(ctx->parent == ruby_repr_current_context);
	ruby_repr_current_context = ctx;
}

static void
__ruby_repr_context_pop(struct ruby_repr_context *ctx)
{
	ruby_repr_buf *child;

	assert(ruby_repr_current_context == ctx);
	ruby_repr_current_context = ctx->parent;

	while ((child = __ruby_repr_context_pop_child(ctx)) != NULL) {
		assert(child->context.children == NULL);
		__ruby_repr_buf_free(child);
	}
}

static ruby_repr_buf *
__ruby_repr_buf_alloc(unsigned int size)
{
	ruby_repr_buf *rbuf;

	/* Note, this actually creates room for size + 1 byte (to store NUL)
	  * because we defined rbuf->data as a one element array */
	rbuf = calloc(1, sizeof(*rbuf) + size + 4);
	rbuf->size = size;
	memcpy((char *) rbuf + size, __parrot, 4);

	__ruby_repr_context_insert(ruby_repr_current_context, rbuf);

	return rbuf;
}

static void
__ruby_repr_buf_free(ruby_repr_buf *rbuf)
{
	assert(!memcmp((char *) rbuf + rbuf->size, __parrot, 4));
	memset(rbuf, 0xa5, sizeof(*rbuf) + rbuf->size + 4);
	free(rbuf);
}

ruby_repr_buf *
__ruby_repr_begin(unsigned int size)
{
	ruby_repr_buf *rbuf;

	rbuf = __ruby_repr_buf_alloc(size);
	__ruby_repr_context_push(&rbuf->context);

	return rbuf;
}

const char *
__ruby_repr_finish(ruby_repr_buf *rbuf)
{
	__ruby_repr_context_pop(&rbuf->context);

	return rbuf->data;
}

const char *
__ruby_repr_abort(ruby_repr_buf *rbuf)
{
	__ruby_repr_context_pop(&rbuf->context);
	return NULL;
}

static inline unsigned int
__ruby_repr_space(const ruby_repr_buf *rbuf)
{
	unsigned int used = rbuf->wpos + rbuf->reserved;

	assert(used < rbuf->size);
	return rbuf->size - used;
}

void
__ruby_repr_reserve_tail(ruby_repr_buf *rbuf, unsigned int tail)
{
	assert(__ruby_repr_space(rbuf) >= tail);

	rbuf->reserved += tail;
}

void
__ruby_repr_unreserve(ruby_repr_buf *rbuf)
{
	rbuf->reserved = 0;
}

static bool
__ruby_repr_put(ruby_repr_buf *rbuf, const char *s, unsigned int n)
{
	if (n > __ruby_repr_space(rbuf))
		return false;
	memcpy(rbuf->data + rbuf->wpos, s, n);
	rbuf->wpos += n;

	assert(rbuf->wpos + rbuf->reserved < rbuf->size);
	return true;
}

bool
__ruby_repr_append(ruby_repr_buf *rbuf, const char *value)
{
	return __ruby_repr_put(rbuf, value, strlen(value));
}

bool
__ruby_repr_appendf(ruby_repr_buf *rbuf, const char *fmt, ...)
{
	char buffer[1024];
	va_list ap;

	va_start(ap, fmt);
	vsnprintf(buffer, sizeof(buffer), fmt, ap);
	va_end(ap);

	return __ruby_repr_append(rbuf, buffer);
}

const char *
__ruby_repr_printf(const char *fmt, ...)
{
	char buffer[1024];
	unsigned int buflen;
	ruby_repr_buf *rbuf;
	va_list ap;

	va_start(ap, fmt);
	vsnprintf(buffer, sizeof(buffer), fmt, ap);
	va_end(ap);

	buflen = strlen(buffer);

	/* allocate an rbuf and attach it to the current context.
	 * We do not open a context of our own */
	rbuf = __ruby_repr_buf_alloc(buflen);

	__ruby_repr_put(rbuf, buffer, buflen);
	assert(rbuf->wpos == buflen);

	return rbuf->data;
}

