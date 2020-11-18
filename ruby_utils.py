#!/usr/bin/python3

import marshal48
import io

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
		# Needed for marshaling
		ruby_classname = 'Gem::Version'

		def __init__(self):
			self.versions = []

		@property
		def version(self):
			return self.versions[0]

		def marshal_load(self, array):
			# print("GemVersion.marshal_load(%s)" % array)
			assert(len(array) == 1)

			for o in array:
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
		# Needed for marshaling
		ruby_classname = 'Gem::Requirement'

		def __init__(self):
			self.req = []

		def marshal_load(self, data):
			# Calls look like
			# GemRequirement.marshal_load([[['>=', 3.0.0]]])
			# print("GemRequirement.marshal_load(%s)" % data)
			for r in data:
				assert(type(r) == list)
				assert(len(r) == 1)
				r = r[0]

				self.req.append(Ruby.Clause(*r))

		def __repr__(self):
			return "[%s]" % (", ".join(str(r) for r in self.req))

		def __contains__(self, item):
			if not isinstance(item, Ruby.ParsedVersion):
				item = Ruby.ParsedVersion(item)

			return all(s.contains(item) for s in self.req)

		def __iter__(self):
			return iter(self.req)

	class GemDependency(object):
		# Needed for marshaling
		ruby_classname = 'Gem::Dependency'

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
			print("GemDependency.parse(%s)" % string)
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
		# Needed for marshaling
		ruby_classname = 'Gem::Specification'

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
			# print("GemSpecification.load(%s)" % data)
			data = unmarshal_byteseq(data)

			gemspec_version = data.pop(0)
			if gemspec_version.startswith("2.") or \
			   gemspec_version.startswith("3."):
				sig = Ruby.GemSpec_2_x.signature
			else:
				if True:
					print("Unknown gemspec version %s" % gemspec_version)
					print("Data:")
					for i in range(len(data)):
						print(i, data[i])

				raise ValueError("Don't know how to deal with gemspec version %s data" % gemspec_version)

			if len(data) != len(sig):
				print("WARNING: GemSpecification.load: gemspec ver %s has %u elements (expected %u)" % (
					gemspec_version, len(data), len(sig)))

			for attr_name, value in zip(sig, data):
				# print("%s=%s" % (attr_name, value))
				setattr(self, attr_name, value)

		def __repr__(self):
			return "GemSpecification(%s-%s)" % (self.name, self.version)

	class Time:
		# Needed for marshaling
		ruby_classname = 'Time'

		def __init__(self):
			self.timedata = None

		def load(self, data):
			# print("Time.load(%s)" % data)
			self.timedata = data

	classes = {
		'Gem::Version'		: GemVersion,
		'Gem::Specification'	: GemSpecification,
		'Gem::Requirement'	: GemRequirement,
		'Gem::Dependency'	: GemDependency,
		'Time'			: Time,
	}

	def find_class(name):
		return Ruby.classes.get(name)

	def factory(name, *args):
		cls = Ruby.find_class(name)
		if not cls:
			raise NotImplementedError("Ruby.factory: unknown class %s" % name)
			print("Ruby.factory: unknown class %s" % name)
			return None

		return cls(*args)

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

	return marshal48.unmarshal(f, Ruby.factory, quiet)

def unmarshal_byteseq(data, quiet = True):

	f = io.BytesIO(data)
	return marshal48.unmarshal(f, Ruby.factory, quiet)
