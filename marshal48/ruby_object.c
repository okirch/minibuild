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


static void		GenericObject_dealloc(marshal48_GenericObject *self);
static PyObject *	GenericObject_new(PyTypeObject *type, PyObject *args, PyObject *kwds);
static PyObject *	GenericObject_set_instance_var(marshal48_GenericObject *self, PyObject *args);
static PyObject *	GenericObject_convert(marshal48_GenericObject *self, PyObject *args);
static PyObject *	GenericObject_construct(marshal48_GenericObject *self, PyObject *args);

static PyMemberDef GenericObject_members[] = {
	{"id", T_INT, offsetof(marshal48_GenericObject, id), 0, "object id"},
	{"classname", T_STRING, offsetof(marshal48_GenericObject, classname), 0, "class name"},

	{ NULL }
};

static PyMethodDef GenericObject_methods[] = {
	{ "set_instance_var", (PyCFunction) GenericObject_set_instance_var, METH_VARARGS, NULL },
	{ "convert", (PyCFunction) GenericObject_convert, METH_NOARGS, NULL },
	{ "construct", (PyCFunction) GenericObject_construct, METH_NOARGS, NULL },
	{ NULL }
};


PyTypeObject marshal48_GenericObjectType = {
	PyVarObject_HEAD_INIT(NULL, 0)

	.tp_name	= "marshal48.GenericObject",
	.tp_basicsize	= sizeof(marshal48_GenericObject),
	.tp_flags	= Py_TPFLAGS_DEFAULT,
	.tp_doc		= "ruby array",

	.tp_init	= (initproc) GenericObject_init,
	.tp_new		= GenericObject_new,
	.tp_dealloc	= (destructor) GenericObject_dealloc,

	.tp_members	= GenericObject_members,
	.tp_methods	= GenericObject_methods,
};

/*
 * Constructor: allocate empty GenericObject object, and set its members.
 */
static PyObject *
GenericObject_new(PyTypeObject *type, PyObject *args, PyObject *kwds)
{
	marshal48_GenericObject *self;

	self = (marshal48_GenericObject *) type->tp_alloc(type, 0);
	if (self == NULL)
		return NULL;

	/* init members */
	self->id = -1;
	self->classname = NULL;
	self->instance_vars = PyDict_New();

	return (PyObject *)self;
}

/*
 * Initialize the array object
 */
int
GenericObject_init(marshal48_GenericObject *self, PyObject *args, PyObject *kwds)
{
	static char *kwlist[] = {
		"classname",
		NULL
	};
	char *classname;

	if (!PyArg_ParseTupleAndKeywords(args, kwds, "s", kwlist, &classname))
		return -1;

	self->classname = strdup(classname);
	self->instance_vars = PyDict_New();
	return 0;
}

/*
 * Destructor: clean any state inside the GenericObject object
 */
static void
GenericObject_dealloc(marshal48_GenericObject *self)
{
	drop_string(&self->classname);
	drop_object(&self->instance_vars);
}

int
GenericObject_Check(PyObject *self)
{
	return PyType_IsSubtype(Py_TYPE(self), &marshal48_GenericObjectType);
}

static PyObject *
GenericObject_instantiate(marshal48_GenericObject *self)
{
	PyObject *instance = NULL, *r;

	/* Look up classname in ruby module and instantiate */
	instance = marshal48_instantiate_ruby_type(self->classname);
	if (instance == NULL)
		return NULL;

	/* This will construct the object */
	r = PyObject_CallMethod((PyObject *) self, "construct", "O", instance);
	if (r == NULL) {
		Py_DECREF(instance);
		return NULL;
	}

	Py_DECREF(r);
	return instance;
}

static bool
GenericObject_apply_instance_vars(marshal48_GenericObject *self, PyObject *instance)
{
	PyObject *key, *value;
	Py_ssize_t pos = 0;

	while (PyDict_Next(self->instance_vars, &pos, &key, &value)) {
		PyObject *attr_val;

		attr_val = PyObject_CallMethod(value, "convert", NULL);
                if (attr_val == NULL)
                        return false;

		if (PyObject_SetAttr(instance, key, attr_val) < 0)
			return false;
	}

	return true;
}

static PyObject *
GenericObject_convert(marshal48_GenericObject *self, PyObject *args)
{
	PyObject *instance = NULL;

	if (!PyArg_Parse(args, ""))
		return NULL;

	if (!(instance = GenericObject_instantiate(self)))
		return NULL;

	if (!GenericObject_apply_instance_vars(self, instance)) {
		Py_DECREF(instance);
		return NULL;
	}

	return instance;
}

static PyObject *
GenericObject_set_instance_var(marshal48_GenericObject *self, PyObject *args)
{
	char *name;
	PyObject *value;

	if (!PyArg_ParseTuple(args, "sO", &name, &value))
		return NULL;

	if (name[0] == '@')
		++name;

	PyDict_SetItemString(self->instance_vars, name, value);
	Py_DECREF(value);

	Py_RETURN_NONE;
}

/*
 * No-op in the base class. This will be overridden in UserMarshal and UserDefined
 */
static PyObject *
GenericObject_construct(marshal48_GenericObject *self, PyObject *args)
{
	Py_RETURN_NONE;
}
