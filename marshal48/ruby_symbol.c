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


static void		Symbol_dealloc(marshal48_Symbol *self);
static PyObject *	Symbol_new(PyTypeObject *type, PyObject *args, PyObject *kwds);

static PyMemberDef Symbol_members[] = {
	{"name", T_STRING, offsetof(marshal48_Symbol, name), 0,
	 "symbol name"},

	{NULL}  /* Sentinel */
};


PyTypeObject marshal48_SymbolType = {
	PyVarObject_HEAD_INIT(NULL, 0)

	.tp_name	= "marshal48.Symbol",
	.tp_basicsize	= sizeof(marshal48_Symbol),
	.tp_flags	= Py_TPFLAGS_DEFAULT,
	.tp_doc		= "ruby symbol",

	.tp_init	= (initproc) Symbol_init,
	.tp_new		= Symbol_new,
	.tp_dealloc	= (destructor) Symbol_dealloc,

	.tp_members	= Symbol_members,
//	.tp_methods	= marshal48_noMethods,
};

/*
 * Constructor: allocate empty Symbol object, and set its members.
 */
static PyObject *
Symbol_new(PyTypeObject *type, PyObject *args, PyObject *kwds)
{
	marshal48_Symbol *self;

	self = (marshal48_Symbol *) type->tp_alloc(type, 0);
	if (self == NULL)
		return NULL;

	/* init members */
	self->name = NULL;

	return (PyObject *)self;
}

/*
 * Initialize the symbol object
 */
int
Symbol_init(marshal48_Symbol *self, PyObject *args, PyObject *kwds)
{
	static char *kwlist[] = {
		"name",
		NULL
	};
	char *symbol;

	if (!PyArg_ParseTupleAndKeywords(args, kwds, "s", kwlist, &symbol))
		return -1;

	self->name = strdup(symbol);

	return 0;
}

/*
 * Destructor: clean any state inside the Symbol object
 */
static void
Symbol_dealloc(marshal48_Symbol *self)
{
	drop_string(&self->name);
}

int
Symbol_Check(PyObject *self)
{
	return PyType_IsSubtype(Py_TYPE(self), &marshal48_SymbolType);
}
