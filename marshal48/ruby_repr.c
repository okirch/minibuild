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
	ruby_repr_buf *	bufs;
};

struct ruby_repr_buf_s {
	ruby_repr_buf *	next;
	ruby_repr_context_t *owner;

	unsigned int	wpos, size, reserved;
	char		data[1];
};

static char		__parrot[4] = { 0xde, 0xad, 0xbe, 0xef }; /* this parrot is dead */


static void		__ruby_repr_buf_free(ruby_repr_buf *rbuf);

static void
__ruby_repr_context_insert(struct ruby_repr_context *ctx, ruby_repr_buf *child)
{
	assert(child->owner == NULL);

	child->owner = ctx;
	child->next = ctx->bufs;
	ctx->bufs = child;
}

static inline ruby_repr_buf *
__ruby_repr_context_pop_child(struct ruby_repr_context *ctx)
{
	ruby_repr_buf *child;

	if ((child = ctx->bufs) != NULL) {
		assert(child->owner == ctx);
		child->owner = NULL;
		ctx->bufs = child->next;
		child->next = NULL;
	}

	return child;
}

static void
ruby_repr_context_destroy(ruby_repr_context_t *ctx)
{
	ruby_repr_buf *child;

	while ((child = __ruby_repr_context_pop_child(ctx)) != NULL)
		__ruby_repr_buf_free(child);

	assert(ctx->bufs == NULL);
}

static unsigned char *
__ruby_repr_parrot_pos(ruby_repr_buf *rbuf)
{
	return ((unsigned char *) rbuf->data) + rbuf->size;
}

static ruby_repr_buf *
__ruby_repr_buf_alloc(ruby_repr_context_t *ctx, unsigned int size)
{
	ruby_repr_buf *rbuf;

	/* Note, this actually creates room for size + 1 byte (to store NUL)
	  * because we defined rbuf->data as a one element array */
	rbuf = calloc(1, sizeof(*rbuf) + size + 4);
	rbuf->size = size;

	memcpy(__ruby_repr_parrot_pos(rbuf), __parrot, 4);

	__ruby_repr_context_insert(ctx, rbuf);
	return rbuf;
}

static void
__ruby_repr_buf_free(ruby_repr_buf *rbuf)
{
	const unsigned char *where = __ruby_repr_parrot_pos(rbuf);

	if (memcmp(where, __parrot, 4)) {
		fprintf(stderr, "%s: bad canary value %02x %02x %02x %02x\n",
				__func__, where[0], where[1], where[2], where[3]);
		abort();
	}

	assert(rbuf->owner == NULL);
	memset(rbuf, 0xa5, sizeof(*rbuf) + rbuf->size + 4);
	free(rbuf);
}

ruby_repr_buf *
__ruby_repr_begin(ruby_repr_context_t *ctx, unsigned int size)
{
	return __ruby_repr_buf_alloc(ctx, size);
}

const char *
__ruby_repr_finish(ruby_repr_buf *rbuf)
{
	return rbuf->data;
}

const char *
__ruby_repr_abort(ruby_repr_buf *rbuf)
{
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
	if (n + 1 > __ruby_repr_space(rbuf))
		return false;
	memcpy(rbuf->data + rbuf->wpos, s, n);
	rbuf->data[rbuf->wpos + n] = '\0';
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
__ruby_repr_printf(ruby_repr_context_t *ctx, const char *fmt, ...)
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
	rbuf = __ruby_repr_buf_alloc(ctx, buflen + 1);

	__ruby_repr_put(rbuf, buffer, buflen);
	assert(rbuf->wpos == buflen);

	return rbuf->data;
}

const char *
__ruby_instance_repr(ruby_instance_t *self, ruby_repr_context_t *ctx)
{
	return self->op->repr(self, ctx);
}

const char *
ruby_instance_repr(ruby_instance_t *self)
{
	static ruby_repr_context_t ctx;
	static bool recursing = false;
	const char *retval;

	if (recursing) {
		fprintf(stderr, "You must not call %s recursively\n", __func__);
		abort();
	}
	recursing = true;

	/* Zap any leftovers from a previous call */
	ruby_repr_context_destroy(&ctx);

	retval = __ruby_instance_repr(self, &ctx);

	recursing = false;
	return retval;
}
