#!/usr/bin/python3

class Ruby:
	class ParsedVersion(object):
		def __init__(self, s):
			self._version = []
			self.is_prerelease = False

			word = None
			isnumber = False
			for cc in s:
				if cc == '.':
					if word is not None:
						self._version.append(word)
					self._version.append('.')
					word = None
					continue

				if word is not None:
					if isnumber == cc.isdigit():
						word += cc;
						continue

					self._version.append(word)

				isnumber = cc.isdigit()
				word = cc

			if word is not None:
				self._version.append(word)

			for i in range(len(self._version)):
				try:
					self._version[i] = int(self._version[i])
				except:
					pass

		def __repr__(self):
			return "".join([str(x) for x in self._version])

		def __lt__(self, other):
			return self.compare(other, lambda s, o: s < o)

		def __gt__(self, other):
			return self.compare(other, lambda s, o: s > o)

		def __le__(self, other):
			return self.compare(other, lambda s, o: s <= o)

		def __ge__(self, other):
			return self.compare(other, lambda s, o: s >= o)

		def __eq__(self, other):
			return self.compare(other, lambda s, o: s == o)

		def __ne__(self, other):
			return self.compare(other, lambda s, o: s != o)

		def compare(self, other, f):
			for a, b in zip(self._version, other._version):
				if a == b:
					continue
				return f(a, b)

			return f(len(self._version), len(other._version))

	class GemVersion(object):
		def __init__(self):
			self.versions = []

		@property
		def version(self):
			return self.versions[0]

		def marshal_load(self, obj):
			assert(isinstance(obj, RubyTypes.Array))
			assert(len(obj.value) == 1)

			for o in obj.value:
				self.versions.append(str(o))

		def __str__(self):
			if len(self.versions) == 1:
				return self.versions[0]
			return "[%s]" % ", ".join(self.versions)

		def __repr__(self):
			if len(self.versions) == 1:
				return self.versions[0]
			return "[%s]" % ", ".join(self.versions)

	class Clause:
		def __init__(self, op, version):
			self.op = op
			self.version = Ruby.ParsedVersion(str(version))

		def __repr__(self):
			return "%s %s" % (self.op, self.version)

		def __contains__(self, item):
			return self.contains(item)

		def contains(self, item):
			op = self.op
			if op == '==':
				return item == self.version
			if op == '!=':
				return item != self.version
			if op == '>=':
				return item >= self.version
			if op == '<=':
				return item <= self.version
			if op == '>':
				return item > self.version
			if op == '<':
				return item < self.version

			raise ValueError("Unknown version comparison operator \"%s\"" % self.op)

	class GemRequirement(object):
		def __init__(self):
			self.req = []

		def marshal_load(self, data):
			assert(isinstance(data, RubyTypes.Array))

			# print("GemRequirement.marshal_load(%s)" % data)
			for r in data.value:
				assert(isinstance(r, RubyTypes.Array))
				assert(len(r.value) == 1)
				r = r.value[0]

				assert(isinstance(r, RubyTypes.Array))
				self.req.append(Ruby.Clause(*(r.convert())))

		def __repr__(self):
			return "[%s]" % (", ".join(str(r) for r in self.req))

		def __contains__(self, item):
			if not isinstance(item, Ruby.ParsedVersion):
				item = Ruby.ParsedVersion(item)

			return all(s.contains(item) for s in self.req)

		def __iter__(self):
			return iter(self.req)

	class GemDependency(object):
		def __init__(self):
			self.name = None
			self.requirement = []
			self.type = 'any'
			self.prerelease = False

		def __repr__(self):
			return "GemDependency(%s %s%s%s)" % (
					self.name,
					str(self.requirement),
					self.type != "runtime" and "; " + self.type or "",
					self.prerelease and "; prerelease" or ""
					)

		def __contains__(self, arg):
			# print("%s.__contains__(%s))" % (self, arg))

			name, version = arg
			if self.name != name:
				return False

			return all(version in r for r in self.requirement)

		def format(self):
			result = self.name + " " + ", ".join([str(x) for x in self.requirement])
			if self.prerelease:
				result += "; prerelease"
			if self.type != 'any':
				result += "; " + self.type
			return result

		@staticmethod
		def parse(string):
			dep = Ruby.GemDependency()

			n = string.find("<>=!~")
			if n < 0:
				dep.name = string
				return dep

			name = string[:n]
			string = string[n:]

			w = string.split(';')
			string = w.pop(0)

			for mod in w:
				mod = mod.replace(' ', '')
				if mod == 'prerelease':
					self.prerelease = True
				else:
					dep.type = mod

			for req in string.split(','):
				req = req.replace(' ', '')

				for i in range(len(req)):
					if req[i] not in "<>=!~":
						break

				dep.requirement.append(Ruby.GemRequirement(req[:i], req[i:]))

			return dep

	@staticmethod
	def parse_dependency(string):
		return Ruby.GemDependency.parse(string)

	class GemSpec_2_x:
		signature = (
				# 'specification_version',
				'unknown1',		# int, usually 4
				'name',			# string
				'version',		# Gem::Version
				'date',			# Time() with instance vars
				'summary',		# string
				'required_ruby_version', # Gem::Dependency
				'required_rubygems_version', # Gem::Dependency
				'platform',		# string
				'dependencies',		# array of Gem::Dependencies
				'unknown2',		# usually empty string
				'email',		# string or array of strings
				'author',		# string or array of strings
				'description',		# string
				'homepage',		# string
				'unknown3',		# boolean
				'unknown4',		# dup of platform (ie "ruby")
				'licenses',		# array of strings
				'metadata',		# hash
		)

	class GemSpecification(object):
		def __init__(self):
			self.name = None
			self.version = None
			self.summary = None
			self.dependencies = None
			self.required_ruby_version = None
			self._required_rubygems_version = None
			self.metadata = None
			self._emails = []
			self._authors = []

		@property
		def email(self):
			if len(self._emails):
				return self._emails[0]
			return None

		@email.setter
		def email(self, value):
			if type(value) == list:
				self._emails = value
			else:
				self._emails = [value]

		@property
		def author(self):
			if len(self._authors):
				return self._authors[0]
			return None

		@author.setter
		def author(self, value):
			if type(value) == list:
				self._authors = value
			else:
				self._authors = [value]

		@property
		def required_rubygems_version(self):
			return self._required_rubygems_version

		@required_rubygems_version.setter
		def required_rubygems_version(self, value):
			if not isinstance(value, Ruby.GemRequirement):
				raise ValueError("marshalled gemspec for %s-%s specifies invalid required_rubygems_version=\"%s\"" % (
					self.name, self.version, value
				))
				return
			self._required_rubygems_version = value

		def load(self, data):
			assert(isinstance(data, RubyTypes.Array))

			gemspec_version = data.value.pop(0).convert()
			if gemspec_version.startswith("2.") or \
			   gemspec_version.startswith("3."):
				sig = Ruby.GemSpec_2_x.signature
			else:
				if True:
					print("Unknown gemspec version %s" % gemspec_version)
					print("Data:")
					for i in range(len(data.value)):
						print(i, data.value[i])

				raise ValueError("Don't know how to deal with gemspec version %s data" % gemspec_version)

			if len(data.value) != len(sig):
				print("WARNING: GemSpecification.load: gemspec ver %s has %u elements (expected %u)" % (
					gemspec_version, len(data.value), len(sig)))

			for attr_name, obj in zip(sig, data.value):
				try:
					if obj is not None and type(obj) != bool:
						value = obj.convert()
				except Exception as e:
					print("Cannot convert() natively:", e)
					value = obj

				# print("%s=%s" % (attr_name, value))
				setattr(self, attr_name, value)

		def __repr__(self):
			return "GemSpecification(%s-%s)" % (self.name, self.version)

	classes = {
		'Gem::Version'		: GemVersion,
		'Gem::Specification'	: GemSpecification,
		'Gem::Requirement'	: GemRequirement,
		'Gem::Dependency'	: GemDependency,
	}

	def find_class(name):
		return Ruby.classes.get(name)

class RubyTypes:
	class Object(object):
		def __init__(self):
			self.id = None

		def __str__(self):
			return str(self.value)

		def convert(self):
			return str(self)

		def set_instance_var(self, name, value):
			self.bad_instance_var(name)

		def bad_instance_var(self, name):
			raise NotImplementedError("%s does not support instance variable @:%s" % (self.__class__.__name__, name))

	class Symbol(Object):
		def __init__(self, name):
			super(RubyTypes.Symbol, self).__init__()
			self.name = name

	class Int(Object):
		def __init__(self, value):
			super(RubyTypes.Int, self).__init__()
			self.value = value

	class String(Object):
		def __init__(self, value):
			super(RubyTypes.String, self).__init__()
			self.value = value

		def set_instance_var(self, name, value):
			if name == 'E':
				if value is True:
					return

				if value is False:
					print("WARN: need to handle string encoding False for \"%s\"" % self.value)
					return

				raise NotImplementedError("Unable to handle string encoding @%s = \"%s\"" % (name, value))

			super(String, self).set_instance_var(name, value)

	class Array(Object):
		def __init__(self):
			super(RubyTypes.Array, self).__init__()
			self.value = []

		def append(self, object):
			self.value.append(object)

		def __str__(self):
			v = self.value
			if len(v) > 10 and False:
				fmt = "[%s, ...]"
				v = v[:10]
			else:
				fmt = "[%s]"
			return fmt % ", ".join([str(member) for member in v])

		def convert(self):
			result = []
			for item in self.value:
				result.append(item.convert())
			return result

	class GenericObject(Object):
		def __init__(self, clazz):
			super(RubyTypes.GenericObject, self).__init__()
			self.clazz = clazz
			self.instance_vars = {}

		@property
		def classname(self):
			return self.clazz

		def set_instance_var(self, name, value):
			if name[0] == '@':
				name = name[1:]
			self.instance_vars[name] = value

		def __str__(self):
			ivars = self._str_instance_vars()
			if ivars:
				return self._constructor() + "; " + ivars

			return self._constructor()

		def _constructor(self):
			return self.clazz + "()"

		def _str_instance_vars(self):
			return ", ".join(["%s=%s" % (name, value) for name, value in self.instance_vars.items()])

		# Converstion to Ruby-esque objects
		def convert(self):
			cls = Ruby.find_class(self.classname)
			if not cls:
				return str(self)

			result = cls()
			self.construct(result)
			return result

		def construct(self, obj):
			for name, value in self.instance_vars.items():
				try:
					value = value.convert()
				except:
					pass
				setattr(obj, name, value)
			return obj

	class UserMarshal(GenericObject):
		def __init__(self, clazz):
			super(RubyTypes.UserMarshal, self).__init__(clazz)
			self.value = None

		def _constructor(self):
			return self.clazz + ".marshal_load(" + str(self.value) + ")"

		def construct(self, obj):
			obj.marshal_load(self.value)
			super(RubyTypes.UserMarshal, self).construct(obj)
			return obj

	class UserDefined(GenericObject):
		def __init__(self, clazz):
			super(RubyTypes.UserDefined, self).__init__(clazz)
			self.data = None

		def _constructor(self):
			if self.data is None:
				return "<>"
			if len(self.data) > 100:
				return self.clazz + ".load(" + str(self.data[:100]) + "...)"
			else:
				return self.clazz + ".load(" + str(self.data) + ")"

		def construct(self, obj):
			if self.data[:2] == b'\x04\x08':
				inner = Unmarshal.from_bytes(self.data, quiet = True)
				obj.load(inner)
			else:
				obj.load(self.data)

			super(RubyTypes.UserDefined, self).construct(obj)
			return obj

	class Hash(Object):
		def __init__(self):
			super(RubyTypes.Hash, self).__init__()
			self.data = {}

		def set(self, key, value):
			self.data[key] = value

		def __str__(self):
			return "Hash(" + ", ".join(["%s=%s" % (key, value) for key, value in self.data.items()]) + ")"

		def convert(self):
			result = {}
			for key, value in self.data.items():
				# print(key, value)
				try:
					key = key.convert()
				except:
					pass

				try:
					value = value.convert()
				except:
					pass

				result[key] = value
			return result

class Unmarshal(object):
	class Indent:
		def __init__(self):
			self.depth = 0
			self.quiet = False

	class IndentIncrement:
		def __init__(self, indent):
			self._indent = indent
			self._indent.depth += 2

		def __del__(self):
			self._indent.depth -= 2

	class Hush:
		def __init__(self, indent):
			self._indent = indent
			self._was_quiet = indent.quiet
			self._indent.quiet = True

		def __del__(self):
			self._indent.quiet = self._was_quiet

	@staticmethod
	def from_file(file, quiet = True):
		u = Unmarshal(file, quiet)
		result = u.process()
		u.assert_done()
		return result

	@staticmethod
	def from_bytes(data, quiet = True):
		import io

		return Unmarshal.from_file(io.BytesIO(data), quiet)

	@staticmethod
	def from_path(path, quiet = True):
		import zlib

		with open(path, 'rb') as f:
			return Unmarshal.from_file(f, quiet)

	@staticmethod
	def from_path_zlib(path, quiet = True):
		import zlib

		with open(path, 'rb') as f:
			data = f.read()

		return Unmarshal.from_bytes(zlib.decompress(data), quiet)

	def __init__(self, file, quiet = True):
		self.f = file

		assert(self.nextb() == 4)
		assert(self.nextb() == 8)

		self._symbols = []
		self._objects = []

		self._indent = Unmarshal.Indent()
		self._indent.quiet = quiet

	def define_symbol(self, name):
		self._symbols.append(RubyTypes.Symbol(name))

	def lookup_symbol(self, index):
		return self._symbols[index]

	def register_object(self, obj):
		if obj.id is None:
			# The documentation for Marshal says that the object index is 1 based.
			# It appears that this is not quite true. On one hand, when decoding an
			# array, the array object will be assigned an ID before its contents.
			# Example (with s = 'thing')
			#   [s, s]  =>		\004\008 [ \007 I " \012 thing ... @ \006
			# IOW the object reference @ \006 indicates that the string is object 1
			#   [[s, s]]  => 	\004\008 [ \006 [ \007 I  " \012 thing ... @ \007
			# Now the object reference is @ \007, so the string becomes object 2
			#   [[[s, s]]]  => 	\004\008 [ \006 [ [ \006 \007 I  " \012 thing ... @ \008
			# Now the object reference is @ \008, so the string becomes object 3
			#
			# At any rate, this means that in general, arrays are assigned an object
			# ID at the time their starting [ is parsed. However, the top-level array
			# is not assigned an object id, or its index must be 0.

			# For the time being, assume that the top-level object has an ID
			# of 0.
			obj.id = len(self._objects)
			self._objects.append(obj)
			# self.display("Registered obj %d = %s" % (obj.id, obj))
		return obj

	def lookup_object(self, index):
		# self.display("object reference %d" % index)
		return self._objects[index]

	def indent(self):
		return Unmarshal.IndentIncrement(self._indent)

	def hush(self):
		return Unmarshal.Hush(self._indent)

	def display(self, msg):
		if not self._indent.quiet:
			print("%s%s" % (self._indent.depth * " ", msg))

	def process(self):
		ii = self.indent()

		cc = self.nextc()
		# self.display("next object = %s" % cc)

		if cc == b'T':
			self.display("True")
			return True
		if cc == b'F':
			self.display("False")
			return False
		if cc == b'0':
			self.display("Nil")
			return None
		if cc == b':':
			return self.process_symbol()
		if cc == b';':
			return self.process_symbol_reference()
		if cc == b'i':
			return self.process_int()
		if cc == b'@':
			return self.process_object_reference()

		if cc == b'[':
			result = self.process_array()
		elif cc == b'I':
			result = self.process_object_with_instance_vars()
		elif cc == b'{':
			result = self.process_hash()
		elif cc == b'o':
			result = self.process_generic_object()
		elif cc == b'"':
			result = self.process_string()
		elif cc == b'U':
			result = self.process_user_marshal()
		elif cc == b'u':
			result = self.process_user_defined()
		else:
			raise NotImplementedError("Unknown object type %s" % cc)

		self.register_object(result)
		self.display("%d: %s = %s" % (result.id, result.__class__.__name__, result))

		return result

	def process_object_reference(self):
		obj_id = self.next_fixnum()
		obj = self.lookup_object(obj_id)
		self.display("Referenced object %d: %s" % (obj_id, obj))
		return obj

	def process_array(self):
		count = self.next_fixnum()
		self.display("Decoding array with %d objects" % count)

		result = RubyTypes.Array()

		# Register the array before we start processing its members;
		# otherwise object references will be off.
		self.register_object(result)

		for i in range(count):
			result.append(self.process())
		return result

	def process_object_with_instance_vars(self):
		h = self.hush()

		object = self.process()

		count = self.next_fixnum()
		self.display("%d instance variable(s) follow" % count)

		for i in range(count):
			name = self.process()
			value = self.process()
			object.set_instance_var(name, value)

		return object

	def process_generic_object(self):
		h = self.hush()

		classname = self.process()

		object = RubyTypes.GenericObject(classname)
		self.register_object(object)

		count = self.next_fixnum()
		self.display("Defining %s with %d instance variable(s)" % (classname, count))

		for i in range(count):
			name = self.process()
			value = self.process()
			object.set_instance_var(name, value)

		return object

	def process_user_marshal(self):
		symbol = self.process()

		object = RubyTypes.UserMarshal(symbol)
		self.register_object(object)

		object.value = self.process()

		return object

	def process_user_defined(self):
		symbol = self.process()

		object = RubyTypes.UserDefined(symbol)
		self.register_object(object)

		object.data = self.next_byteseq()
		return object

	def process_hash(self):
		result = RubyTypes.Hash()
		size = self.next_fixnum()

		for i in range(size):
			key = self.process()
			value = self.process()
			result.set(key, value)

		return result

	def process_symbol(self):
		# self.display("Decoding symbol")
		name = self.next_string()
		self.define_symbol(name)
		self.display("Defined symbol \"%s\"" % name)
		return name

	def process_symbol_reference(self):
		# self.display("Decoding symbol reference")
		ref = self.next_fixnum()
		sym = self.lookup_symbol(ref)
		self.display("Referenced symbol \"%s\"" % sym.name)
		return sym.name

	def process_int(self):
		return RubyTypes.Int(self.next_fixnum())

	def process_string(self):
		count = self.next_fixnum()
		result = self.f.read(count).decode('latin1')

		return RubyTypes.String(result)

	def next_string(self):
		return self.next_byteseq().decode('latin1')

	def next_byteseq(self):
		count = self.next_fixnum()
		return self.f.read(count)

	def next_fixnum(self):
		cc = self.nextb()
		# self.display("int0=0x%x" % cc)

		if cc == 0:
			return 0
		elif cc in (1, 2, 3):
			return self.nextw(cc)
		elif cc == 0xff:
			return 1 - self.nextb()
		elif cc == 0xfe:
			pass
		elif cc == 0xfd:
			pass
		elif cc == 0xfc:
			pass
		else:
			if cc < 0x80:
				return cc - 5
			return 0x80 - cc - 5

		raise NotImplementedError("Integer type 0x%x" % cc)

	def nextb(self):
		cc = self.nextc()
		return int.from_bytes(cc, byteorder = 'little')

	def nextw(self, count):
		bytes = self.bytes(count)
		return int.from_bytes(bytes, byteorder = 'little')

	def nextc(self):
		return self.f.read(1)

	def bytes(self, count):
		return self.f.read(count)

	def assert_done(self):
		assert(self.f.read() == b'')

class DecompressNone:
	@staticmethod
	def open(fileobj):
		return fileobj

class DecompressGzip:
	@staticmethod
	def open(fileobj):
		import gzip

		return gzip.GzipFile(fileobj = fileobj, mode = 'rb')

class DecompressZlib:
	@staticmethod
	def open(fileobj):
		import zlib
		import io

		data = zlib.decompress(fileobj.read())
		return io.BytesIO(data)

def guess_compression(url_or_path):
	if url_or_path.endswith(".gz"):
		return DecompressGzip
	if url_or_path.endswith(".rz"):
		return DecompressZlib
	return DecompressNone

def unmarshal(url_or_path, f = None, quiet = True):
	decompressor = guess_compression(url_or_path)
	if f is None:
		f = open(url_or_path, mode = 'rb')
	f = decompressor.open(f)

	obj = Unmarshal.from_file(f, quiet)
	del f

	return obj.convert()
