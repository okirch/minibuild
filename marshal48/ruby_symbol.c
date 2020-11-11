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


#include <Python.h>
#include <structmember.h>

#include "extension.h"
#include "ruby_impl.h"

typedef struct {
	ruby_instance_t	sym_base;
	char *		sym_name;
} ruby_Symbol;


static void
ruby_Symbol_del(ruby_Symbol *self)
{
	drop_string(&self->sym_name);
	__ruby_instance_del((ruby_instance_t *) self);
}

static const char *
ruby_Symbol_repr(ruby_Symbol *self)
{
	if (self->sym_name == NULL)
		return "<NUL>";

	return self->sym_name;
}

static ruby_type_t ruby_Symbol_methods = {
	.name		= "Symbol",
	.size		= sizeof(ruby_Symbol),
	.registration	= RUBY_REG_SYMBOL,

	.del		= (ruby_instance_del_fn_t) ruby_Symbol_del,
	.repr		= (ruby_instance_repr_fn_t) ruby_Symbol_repr,
};

ruby_instance_t *
ruby_Symbol_new(ruby_context_t *ctx, const char *name)
{
	ruby_Symbol *sym;

	sym = (ruby_Symbol *) __ruby_instance_new(ctx, &ruby_Symbol_methods);
	sym->sym_name = strdup(name);

	return (ruby_instance_t *) sym;
}

bool
ruby_Symbol_check(const ruby_instance_t *self)
{
	return self->op == &ruby_Symbol_methods;
}

const char *
ruby_Symbol_get_name(const ruby_instance_t *self)
{
	if (!ruby_Symbol_check(self))
		return NULL;
	return ((ruby_Symbol *) self)->sym_name;
}
