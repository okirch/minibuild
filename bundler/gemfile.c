/*
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
#include "gemfile.h"

typedef struct bundler_Context {
	PyObject_HEAD

	bundler_context_t *	handle;
} bundler_Context;

typedef struct bundler_Gemfile {
	PyObject_HEAD

	bundler_gemfile_t *	handle;
} bundler_Gemfile;

static void		Gemfile_dealloc(bundler_Gemfile *self);
static PyObject *	Gemfile_new(PyTypeObject *type, PyObject *args, PyObject *kwds);
static int		Gemfile_init(bundler_Gemfile *self, PyObject *args, PyObject *kwds);
static PyObject *	Gemfile_getattr(bundler_Gemfile *self, char *name);
static PyObject *	Gemfile_required(bundler_Gemfile *self, PyObject *args, PyObject *kwds);
static PyObject *	Gemfile_show(bundler_Gemfile *self, PyObject *args, PyObject *kwds);

static void		Context_dealloc(bundler_Context *self);
static PyObject *	Context_new(PyTypeObject *type, PyObject *args, PyObject *kwds);
static int		Context_init(bundler_Context *self, PyObject *args, PyObject *kwds);
static PyObject *	Context_getattr(bundler_Context *self, char *name);
static int		Context_setattr(bundler_Context *self, char *name, PyObject *value);
static PyObject *	Context_with_group(bundler_Context *self, PyObject *args, PyObject *kwds);
static PyObject *	Context_without_group(bundler_Context *self, PyObject *args, PyObject *kwds);


/*
 * Define the python bindings of class "Gemfile"
 *
 * Create objects using
 *   gemfile = bundler.Gemfile(path, context = ctx)
 *
 * You can query the content of the Gemfile like this
 *   gemfile.required()
 */
static PyMethodDef bundler_gemfileMethods[] = {
      {	"required", (PyCFunction) Gemfile_required, METH_VARARGS | METH_KEYWORDS,
	"Obtain the list of gems required"
      },
      {	"show", (PyCFunction) Gemfile_show, METH_VARARGS | METH_KEYWORDS,
	"Dump contents of gemfile to stdout"
      },

      {	NULL }
};

PyTypeObject bundler_GemfileType = {
	PyVarObject_HEAD_INIT(NULL, 0)

	.tp_name	= "bundler.Gemfile",
	.tp_basicsize	= sizeof(bundler_Gemfile),
	.tp_flags	= Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE,
	.tp_doc		= "Bundler Gemfile",

	.tp_methods	= bundler_gemfileMethods,
	.tp_init	= (initproc) Gemfile_init,
	.tp_new		= Gemfile_new,
	.tp_dealloc	= (destructor) Gemfile_dealloc,

	.tp_getattr	= (getattrfunc) Gemfile_getattr,
};

/*
 * Constructor: allocate empty Target object, and set its members.
 */
static PyObject *
Gemfile_new(PyTypeObject *type, PyObject *args, PyObject *kwds)
{
	bundler_Gemfile *self;

	self = (bundler_Gemfile *) type->tp_alloc(type, 0);
	if (self == NULL)
		return NULL;

	/* init members */
	self->handle = NULL;

	return (PyObject *)self;
}

static int
Gemfile_init(bundler_Gemfile *self, PyObject *args, PyObject *kwds)
{
	static char *kwlist[] = {"path", "context", NULL};
	char *path;
	gemfile_parse_error_t *parse_err = NULL;
	PyObject *contextObj = NULL;
	bundler_context_t *ctx = NULL;

	if (!PyArg_ParseTupleAndKeywords(args, kwds, "s|O", kwlist, &path, &contextObj))
		return -1; 

	if (contextObj && contextObj->ob_type == &bundler_ContextType)
		ctx = ((bundler_Context *) contextObj)->handle;

	self->handle = bundler_gemfile_parse(path, ctx, &parse_err);
	if (self->handle == NULL) {
		if (parse_err == NULL) {
			PyErr_SetString(PyExc_ValueError, "Failed to parse gemfile");
		} else {
			PyErr_Format(PyExc_SyntaxError,
					"Failed to parse gemfile: %s", parse_err->lines[0]);
			PyErr_SyntaxLocation(parse_err->filename, parse_err->lineno);

			gemfile_parse_error_free(parse_err);
		}

		return -1;
	}

	return 0;
}

/*
 * Destructor: clean any state inside the Target object
 */
static void
Gemfile_dealloc(bundler_Gemfile *self)
{
	if (self->handle)
		bundler_gemfile_free(self->handle);
	self->handle = NULL;
}

static PyObject *
Gemfile_getattr(bundler_Gemfile *self, char *name)
{
	if (!strcmp(name, "source"))
		return return_string_or_none(self->handle->source);

	return PyObject_GenericGetAttr((PyObject *) self, PyUnicode_FromString(name));
}

static PyObject *
Gemfile_required(bundler_Gemfile *self, PyObject *args, PyObject *kwds)
{
	static char *kwlist[] = {NULL};
	bundler_gemfile_t *gemf;
	unsigned int i, count, index;
	PyObject *result;

	if (!PyArg_ParseTupleAndKeywords(args, kwds, "", kwlist))
		return NULL;

	gemf = self->handle;
	for (i = count = 0; i < gemf->gems.count; ++i) {
		bundler_gem_t *gem = (bundler_gem_t *) gemf->gems.value[i];

		if (!gem->ignore)
			count++;
	}

	result = PyTuple_New(count);
	for (i = index = 0; i < gemf->gems.count; ++i) {
		bundler_gem_t *gem = (bundler_gem_t *) gemf->gems.value[i];
		const char *req_string;

		if (gem->ignore)
			continue;

		req_string = bundler_gem_as_requirement(gem);

		PyTuple_SET_ITEM(result, index++, PyUnicode_FromString(req_string));
	}

	return result;
}

static PyObject *
Gemfile_show(bundler_Gemfile *self, PyObject *args, PyObject *kwds)
{
	static char *kwlist[] = {NULL};

	if (!PyArg_ParseTupleAndKeywords(args, kwds, "", kwlist))
		return NULL;

	bundler_gemfile_show(self->handle);

	Py_RETURN_NONE;
}



/*
 * Define the python bindings of class "Context"
 */
static PyMethodDef bundler_contextMethods[] = {
      {	"with_group", (PyCFunction) Context_with_group, METH_VARARGS | METH_KEYWORDS,
	"Select groups of gems to enable"
      },
      {	"without_group", (PyCFunction) Context_without_group, METH_VARARGS | METH_KEYWORDS,
	"Select groups of gems to disable"
      },

      {	NULL }
};

PyTypeObject bundler_ContextType = {
	PyVarObject_HEAD_INIT(NULL, 0)

	.tp_name	= "bundler.Context",
	.tp_basicsize	= sizeof(bundler_Context),
	.tp_flags	= Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE,
	.tp_doc		= "Bundler Context",

	.tp_methods	= bundler_contextMethods,
	.tp_init	= (initproc) Context_init,
	.tp_new		= Context_new,
	.tp_dealloc	= (destructor) Context_dealloc,

	.tp_getattr	= (getattrfunc) Context_getattr,
	.tp_setattr	= (setattrfunc) Context_setattr,
};

/*
 * Constructor: allocate empty Target object, and set its members.
 */
static PyObject *
Context_new(PyTypeObject *type, PyObject *args, PyObject *kwds)
{
	bundler_Context *self;

	self = (bundler_Context *) type->tp_alloc(type, 0);
	if (self == NULL)
		return NULL;

	/* init members */
	self->handle = NULL;

	return (PyObject *)self;
}

static int
Context_init(bundler_Context *self, PyObject *args, PyObject *kwds)
{
	static char *kwlist[] = {"ruby_version", NULL};
	char *ruby_version = NULL;

	if (!PyArg_ParseTupleAndKeywords(args, kwds, "|s", kwlist, &ruby_version))
		return -1; 

	self->handle = bundler_context_new(ruby_version);
	if (self->handle == NULL) {
		PyErr_Format(PyExc_ValueError, "Failed to create bundler context");
		return -1;
	}

	return 0;
}

/*
 * Destructor: clean any state inside the Target object
 */
static void
Context_dealloc(bundler_Context *self)
{
	if (self->handle)
		bundler_context_free(self->handle);
	self->handle = NULL;
}

static PyObject *
Context_getattr(bundler_Context *self, char *name)
{
	if (!strcmp(name, "debug")) {
		if (bundler_context_get_debug(self->handle))
			Py_RETURN_TRUE;
		else
			Py_RETURN_FALSE;
	}

	return PyObject_GenericGetAttr((PyObject *) self, PyUnicode_FromString(name));
}

static int
Context_setattr(bundler_Context *self, char *name, PyObject *value)
{
	if (!strcmp(name, "debug")) {
		bundler_context_set_debug(self->handle, PyObject_IsTrue(value));
		return 0;
	}

	return PyObject_GenericSetAttr((PyObject *) self, PyUnicode_FromString(name), value);
}

static PyObject *
Context_with_group(bundler_Context *self, PyObject *args, PyObject *kwds)
{
	static char *kwlist[] = {"group", NULL};
	char *name = NULL;

	if (!PyArg_ParseTupleAndKeywords(args, kwds, "s", kwlist, &name))
		return NULL;

	bundler_context_with_group(self->handle, name);

	Py_RETURN_NONE;
}

static PyObject *
Context_without_group(bundler_Context *self, PyObject *args, PyObject *kwds)
{
	static char *kwlist[] = {"group", NULL};
	char *name = NULL;

	if (!PyArg_ParseTupleAndKeywords(args, kwds, "s", kwlist, &name))
		return NULL;

	bundler_context_without_group(self->handle, name);

	Py_RETURN_NONE;
}

