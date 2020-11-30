#!/usr/bin/python3
#
# This is a simplistic build script for building artefacts of various
# programming languages natively (eg using pip, npm etc) and upload the
# resulting artefacts to a local repo.
#
#   Copyright (C) 2020 Olaf Kirch <okir@suse.de>
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published by
#   the Free Software Foundation; either version 2 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU General Public License for more details.
#
#   You should have received a copy of the GNU General Public License
#   along with this program; if not, write to the Free Software
#   Foundation, Inc., 675 Mass Ave, Cambridge, MA 02139, USA.
#

import sys
import os
import os.path
import io
import glob
import shutil

def __pre_command():
	# Avoid messing up the order of our output and the output of subprocesses when
	# stdout is redirected
	sys.stdout.flush()
	sys.stderr.flush()

def run_command(cmd, ignore_exitcode = False):
	print("Running %s" % cmd)

	__pre_command()
	if os.system(cmd) != 0 and not ignore_exitcode:
		raise ValueError("Command `%s' returned non-zero exit status" % cmd)

def popen(cmd, mode = 'r'):
	print("Running %s" % cmd)

	__pre_command()
	return os.popen(cmd, mode)

class Object(object):
	def mni(self):
		import sys
		import traceback
		import threading

		my_thread = threading.current_thread()
		for thread, frame in sys._current_frames().items():
			if thread != my_thread.ident:
				continue

			if frame.f_code.co_name != 'mni':
				break

			frame = frame.f_back
			raise NotImplementedError("%s.%s(): method not implemented" % (self.__class__.__name__, frame.f_code.co_name))

		# we were trying to be too clever; or something changed in the way python handles stack frames.
		# Fall back to a more bland error message
		raise NotImplementedError("%s: method not implemented" % (self.__class__.__name__))

class ArtefactAttrs(Object):
	engine = "UNKNOWN"

	def __init__(self, name, version = None):
		self.name = name
		self.version = version
		self.hash = {}

	def __repr__(self):
		return self.id()

	def id(self):
		if not self.version:
			return self.name
		return "%s-%s" % (self.name, self.version)

	def get_hash(self, algo):
		return self.hash.get(algo)

	def add_hash(self, algo, md):
		self.hash[algo] = md

	# Subclasses that implement different fingerprinting methods
	# should override this
	# (Or we should remove it here and create a mixin class instead)
	def update_hash(self, algo):
		import hashlib

		m = hashlib.new(algo)
		with open(self.local_path, "rb") as f:
			m.update(f.read())

		self.add_hash(algo, m.hexdigest())

class BuildRequirement(ArtefactAttrs):
	def __init__(self, name, req_string = None, cooked_requirement = None):
		super(BuildRequirement, self).__init__(name)

		if req_string and not cooked_requirement:
			self.parse_requirement(req_string)
		else:
			self.req_string = req_string
			self.cooked_requirement = cooked_requirement

		self.resolution = None

	def parse_requirement(self, req_string):
		self.mni()

	def __repr__(self):
		if self.cooked_requirement:
			return repr(self.cooked_requirement)
		if self.req_string:
			return self.req_string
		return self.name

class Artefact(ArtefactAttrs):
	def __init__(self, name, version = None):
		super(Artefact, self).__init__(name, version)

		self.url = None
		self.local_path = None

	def __repr__(self):
		return "%s(%s)" % (self.__class__.__name__, self.id())

	def git_url(self):
		self.mni()

	@property
	def is_source(self):
		self.mni()

class PackageReleaseInfo(Object):
	def __init__(self, name, version):
		self.name = name
		self.version = version

		self.builds = []

	def id(self):
		self.mni()

	def more_recent_than(self, other):
		self.mni()

	def add_build(self, build):
		self.builds.append(build)

class PackageInfo(Object):
	def __init__(self, name):
		self.name = name
		self.releases = []

	def add_release(self, release):
		self.releases.append(release)

	def versions(self):
		return [r.version for r in self.releases]

class DownloadFinder(Object):
	def __init__(self, verbose):
		self.verbose = verbose

	def get_best_match(self, index):
		self.mni()

class PackageIndex(Object):
	def get_package_info(self, name):
		self.mni()

class HTTPPackageIndex(PackageIndex):
	def __init__(self, url):
		self.url = url
		self._pkg_url_template = None

	def get_package_info(self, name):
		import urllib.request

		url = self._pkg_url_template.format(index_url = self.url, pkg_name = name)

		resp = urllib.request.urlopen(url)
		if resp.status != 200:
			raise ValueError("Unable to get package info for %s: HTTP response %s (%s)" % (
					name, resp.status, resp.reason))

		return self.process_package_info(name, resp)

	# returns a PackageInfo object
	def process_package_info(self, name, http_resp):
		self.mni()

# For now, this is a very trivial downloader.
# This could be something much more complex that uses caches, OBS, yadda yadda
class Downloader(object):
	def __init__(self):
		pass

	def download(self, build, destdir = None):
		import urllib.request

		if build.local_path:
			return build.local_path

		assert(build.url)
		assert(build.filename)

		url = build.url
		resp = urllib.request.urlopen(url)
		if resp.status != 200:
			raise ValueError("Unable to download %s from %s (HTTP status %s %s)" % (
					build.filename, url, resp.status, resp.reason))

		filename = build.filename
		if destdir:
			filename = os.path.join(destdir, filename)

		with open(filename, "wb") as f:
			f.write(resp.read())

		print("Downloaded %s from %s" % (filename, url))

		build.local_path = filename
		return filename

# For now, a very trivial uploader.
class Uploader(Object):
	def __init__(self):
		pass

	def describe(self):
		self.mni()

	def upload(self, build):
		self.mni()

class BuildInfo(Object):
	def __init__(self, engine):
		self.engine = engine
		self.requires = []
		self.artefacts = []

	def add_requirement(self, req):
		self.requires.append(req)

	def add_artefact(self, build):
		self.artefacts.append(build)

	def save(self, path):
		with open(path, "w") as f:
			f.write("engine %s\n" % self.engine)
			self.write_build_requires(f)
			self.write_artefacts(f)

	#
	# Write out the build-requires information
	#
	def write_build_requires(self, f):
		for req in self.requires:
			f.write("require %s %s\n" % (req.engine, req))
			if req.hash:
				for (algo, md) in req.hash.items():
					f.write("  hash %s %s\n" % (algo, md))

			artefact = req.resolution
			if artefact:
				if artefact.filename:
					print("  filename %s" % artefact.filename, file = f)
				if artefact.url:
					print("  url %s" % artefact.url, file = f)

	def write_artefacts(self, f):
		for build in self.artefacts:
			f.write("artefact %s %s %s %s\n" % (build.engine, build.name, build.version, build.type))
			f.write("  filename %s\n" % build.filename)

			for (algo, md) in build.hash.items():
				f.write("  hash %s %s\n" % (algo, md))

	#
	# Parse the build-requires file
	#
	@staticmethod
	def from_file(path, config, default_engine = None):
		print("Loading build info from %s" % path)
		result = BuildInfo(None)

		engine = default_engine
		with open(path, 'r') as f:
			req = None
			for l in f.readlines():
				if not l:
					continue

				if not l.startswith(' '):
					# reset the engine
					engine = None
					obj = None

					(kwd, l) = l.split(maxsplit = 1)

					if kwd == 'engine':
						if result.engine:
							raise ValueError("%s: duplicate engine specification" % path)
						result.engine = l.strip()
						if default_engine and result.engine != default_engine.name:
							raise ValueError("Beware, %s specifies engine \"%s\" which conflicts with engine %s" % (
								path, result.engine, default_engine.name))
						continue

					if kwd in ('require', 'artefact'):
						(name, l) = l.split(maxsplit = 1)
						engine = Engine.factory(name, config, {})

						if kwd == 'require':
							obj = engine.parse_build_requirement(l.strip())
							result.add_requirement(obj)
						elif kwd == 'artefact':
							args = l.split()
							obj = engine.create_artefact_from_NVT(*args)
							result.add_artefact(obj)
						continue
					else:
						raise ValueError("%s: unexpected keyword \"%s\"" % (path, kwd))
				else:
					words = l.split()
					kwd = words.pop(0)

					if kwd == 'hash':
						obj.add_hash(words[0], words[1])
					elif kwd == 'filename':
						# This is not quite right for Requirements objects
						obj.filename = words[0]
					elif kwd == 'url':
						# This is not quite right for Requirements objects
						obj.url = words[0]
					else:
						raise ValueError("%s: unparseable line <%s>" % (path, l))

		if result.engine is None:
			raise ValueError("%s: missing engine specification" % path)
		return result


class BuildDirectory(Object):
	def __init__(self, compute, build_base):
		self.compute = compute
		self.build_base = self.compute.get_directory(build_base)
		self.directory = None
		self.sdist = None
		self.quiet = False
		self.build_log = None

		self.build_info = None

	def cleanup(self):
		if self.directory:
			self.directory.rmtree()

	@property
	def location(self):
		return self.build_base.path

	def set_logging(self, quiet = None, build_log = None):
		if quiet is not None:
			self.quiet = quiet
		if build_log is not None:
			self.build_log = build_log

	def unpacked_dir(self):
		if not self.directory:
			return "<none>"

		return self.directory.path

	def unpack_archive(self, sdist):
		archive = sdist.local_path
		if not archive or not os.path.exists(archive):
			raise ValueError("Unable to unpack %s: you need to download the archive first" % sdist.filename)

		relative_unpack_dir = self.archive_get_unpack_directory(sdist)

		d = self.build_base.lookup(relative_unpack_dir)
		if d is not None:
			d.rmtree()

		shutil.unpack_archive(archive, self.build_base.hostpath())

		self.directory = self.build_base.lookup(relative_unpack_dir)
		if not self.directory or not self.directory.isdir():
			raise ValueError("Unpacking %s failed: cannot find %s in %s" % (archive, relative_unpack_dir, self.build_base.path))

		self.sdist = sdist

	def unpack_git(self, sdist, destdir):
		repo_url = sdist.git_url()
		if not repo_url:
			raise ValueError("Unable to build from git - cannot determine git url")

		self.unpack_git_helper(repo_url, tag = sdist.version, destdir = sdist.id())
		self.sdist = sdist

	# General helper function: clone a git repo to the given destdir, and
	# optionally check out the tag requested (HEAD otherwise)
	def unpack_git_helper(self, git_repo, tag = None, destdir = None):
		assert(destdir) # for now

		if destdir:
			self.compute.run_command("git clone %s %s" % (git_repo, destdir))
		else:
			self.compute.run_command("git clone %s" % (git_repo))

		if tag:
			self.compute.run_command("git checkout %s" % tag, working_dir = destdir)

	def build(self):
		self.mni()

	def build_command_helper(self, cmd):
		assert(self.directory)

		if self.build_log:
			log = open(self.build_log, "w")
			f = self.compute.popen(cmd, working_dir = self.directory)
			line = f.readline()
			while line:
				if not self.quiet:
					print(line.rstrip())
				log.write(line)

				line = f.readline()

			log.close()

			print("Command output written to %s" % self.build_log)

			if f.close():
				raise ValueError("Command `%s' returned non-zero exit status" % cmd)
		else:
			cmd += " >/dev/null 2>&1"
			self.compute.run_command(cmd, working_dir = self.directory)

	def unchanged_from_previous_build(self, build_state):
		self.mni()

	def guess_build_dependencies(self):
		self.mni()

	def finalize_build_depdendencies(self, downloader):
		self.mni()

	def prepare_results(self, build_state):
		self.build_info.save(build_state.get_new_path("build-info"))

		for build in self.build_info.artefacts:
			build.local_path = build_state.save_file(build.local_path)

	def build_requires_as_string(self):
		self.mni()

	def unchanged_from_previous_build(self, build_state):
		if not build_state.exists():
			print("%s was never built before" % self.sdist.id())
			return False

		samesame = True
		for build in self.build_info.artefacts:
			artefact_name = os.path.basename(build.local_path)

			if build.is_source:
				print("Not checking %s..." % (artefact_name))
				continue

			new_path = build.local_path
			old_path = build_state.get_old_path(artefact_name)
			print("Checking %s vs %s" % (new_path, old_path))
			if not os.path.exists(old_path):
				print("%s does not exist" % old_path)
				samesame = False
				continue

			if not self.artefacts_identical(old_path, new_path):
				print("%s differs from previous build" % artefact_name)
				samesame = False
				continue

		path = build_state.get_old_path("build-info")
		if not os.path.exists(path):
			print("Previous build of %s did not write a build-info file" % self.sdist.id())
			samesame = False
		else:
			new_path = build_state.get_new_path("build-info")

			with open(path, "r") as old_f:
				with open(new_path, "r") as new_f:
					if old_f.read() != new_f.read():
						print("Build info changed")
						run_command("diff -u %s %s" % (path, new_path), ignore_exitcode = True)
						samesame = False

		return samesame

	def artefacts_identical(self, old_path, new_path):
		def print_delta(path, how, name_set):
			print("%s: %s %d file(s)" % (path, how, len(name_set)))
			for name in name_set:
				print("  %s" % name)

		added_set, removed_set, changed_set = self.compare_build_artefacts(old_path, new_path)

		samesame = True
		if added_set:
			print_delta(new_path, "added", added_set)
			samesame = False

		if removed_set:
			print_delta(new_path, "removed", removed_set)
			samesame = False

		if changed_set:
			print_delta(new_path, "changed", changed_set)
			samesame = False

		if samesame:
			print("%s: unchanged" % new_path)

		return samesame

class BuildState(Object):
	def __init__(self, engine, savedir):
		import tempfile

		self.engine = engine
		self.savedir = savedir
		self.tmpdir = tempfile.TemporaryDirectory(prefix = "brcoti-")

	def __del__(self):
		self.cleanup()

	def exists(self):
		return os.path.exists(self.savedir)

	def build_log_file(self):
		return os.path.join(self.tmpdir.name, "build.log")

	def commit(self):
		if not self.tmpdir:
			print("%s: changes already committed" % self.savedir)
			return

		# Clean up the savedir
		if os.path.exists(self.savedir):
			shutil.rmtree(self.savedir)
		os.makedirs(self.savedir, mode = 0o755)

		# And copy our data over it
		print("Committing build state to %s:" % self.savedir, end = ' ')
		for file in glob.glob(os.path.join(self.tmpdir.name, "*")):
			print(os.path.basename(file), end = ' ')
			shutil.copy(file, self.savedir)
		print("")

	def cleanup(self):
		if self.tmpdir:
			del self.tmpdir
		self.tmpdir = None

	def get_old_path(self, name):
		return os.path.join(self.savedir, name)

	def get_new_path(self, name):
		return os.path.join(self.tmpdir.name, name)

	def maybe_save_file(self, src, dst = None):
		if not os.path.exists(src):
			print("Not saving %s (does not exist)" % src)
			return None

		return self.save_file(src, dst)

	def save_file(self, src):
		dst = self.tmpdir.name

		print("Saving %s to %s" % (src, dst))

		if isinstance(src, ComputeResourceFS):
			src = src.hostpath()
		shutil.copy(src, dst)

		if os.path.isdir(dst):
			return os.path.join(dst, os.path.basename(src))
		return dst

	def write_file(self, name, data, desc = None):
		path = self.get_new_path(name)

		if desc:
			print("Writing %s to %s" % (desc, path))
		else:
			print("Writing %s" % path)
		with open(path, "w") as f:
			f.write(data)

	def rebuild_required(self):
		path = self.get_old_path("build-info")
		if not os.path.exists(path):
			print("Previous build did not create a build-info file")
			return True

		try:
			engine = self.engine
			build_info = BuildInfo.from_file(path, engine.config, default_engine = engine)
		except Exception as e:
			print("Cannot parse build-info file at %s" % path)
			print(e)
			return True

		for req in build_info.requires:
			if self.build_changed(req):
				return True

		return False

	def build_changed(self, req):
		print("Build requires %s" % req)

		p = self.engine.resolve_build_requirement(req)

		print("  Best match available from package index: %s" % p.filename)
		if req.version:
			if req.version != p.version:
				print("Building would pick %s-%s rather than %s-%s" % (
					p.name, p.version,
					req.name, req.version))
				return True

		match = False
		for algo, md in req.hash.items():
			print("  We are looking for %s %s %s" % (req.id(), algo, md))
			have_md = p.hash.get(algo)
			if have_md is None:
				print("  => index does not provide %s hash for %s" % (algo, p.filename))
				continue

			print("  => index provides %s %s %s" % (p.filename, algo, p.hash.get(algo)))
			if have_md == md:
				match = True

		if not match:
			print("%s was apparently rebuilt in the meantime, we need to rebuild" % p.filename)
			return True

		print("Build requirement did not change")

class Publisher(Object):
	def __init__(self, type, repconfig):
		self.type = type
		self.repoconfig = repconfig

	# TBD: implement a two-stage process where we first
	# create the updated hierarchy in a temporary location,
	# and then rename it to the final location (more or less
	# atomically).

	def commit(self):
		pass

	def prepare_repo_dir(self):
		path = self.repoconfig.url

		if not path.startswith("/"):
			raise ValueError("Cannot create publisher for URL \"%s\"" % path)

		if os.path.exists(path):
			shutil.rmtree(path)

		self.repo_dir = path
		os.makedirs(self.repo_dir, mode = 0o755)

		return path

	def prepare_repo_subdir(self, relative_path):
		path = os.path.join(self.repo_dir, relative_path)
		os.makedirs(path)
		return path

class ComputeResourceFS(Object):
	def __init__(self, path):
		self.path = path

	def __repr__(self):
		return self.path

	def basename(self):
		return os.path.basename(self.path)

	def rmtree(self):
		path = self.hostpath()
		if os.path.exists(path):
			print("Recursively remove %s" % path)
			shutil.rmtree(path)

	def hostpath(self):
		self.mni()

class ComputeResourceFile(ComputeResourceFS):
	def __init__(self, path):
		super(ComputeResourceFile, self).__init__(path)

	def open(self, mode = 'r'):
		self.mni()

	def isreg(self):
		return True

	def isdir(self):
		return False

class ComputeResourceDirectory(ComputeResourceFS):
	def __init__(self, path):
		super(ComputeResourceDirectory, self).__init__(path)

	def file_exists(self, path):
		self.mni()

	def lookup(self, path):
		self.mni()

	def open(self, path, mode = 'r'):
		self.mni()

	def glob_files(self, path_pattern):
		self.mni()

	def isreg(self):
		return False

	def isdir(self):
		return True

class ComputeNode(Object):
	def __init__(self, backend):
		self.backend = backend
		self.cleanup_on_exit = True

	def noclean(self):
		self.cleanup_on_exit = False

	def default_build_dir(self):
		return self.backend.default_build_dir()

	def translate_url(self, url):
		return url

	def trusted_hosts(self):
		return []

	def putenv(self, name, value):
		self.mni()

	def run_command(self, cmd, working_dir = None, ignore_exitcode = False, privileged_user = False):
		if not working_dir:
			print("Running %s" % cmd)
		else:
			print("Running %s [in directory %s]" % (cmd, working_dir))

		# Avoid messing up the order of our output and the output of subprocesses when
		# stdout is redirected
		sys.stdout.flush()
		sys.stderr.flush()

		exit_code = self._run_command(cmd, working_dir, privileged_user)

		if exit_code != 0 and not ignore_exitcode:
			raise ValueError("Command `%s' returned non-zero exit status" % cmd)

		return exit_code

	def _run_commandx(self, cmd, working_dir = None):
		self.mni()

	def popen(self, cmd, mode = 'r', working_dir = None):
		print("Running %s" % cmd)

		# For now...
		assert(mode == 'r')

		# Avoid messing up the order of our output and the output of subprocesses when
		# stdout is redirected
		sys.stdout.flush()
		sys.stderr.flush()

		return self._popen(cmd, mode, working_dir = working_dir)

	def _popen(self, cmd, mode):
		self.mni()

	def get_directory(self, path):
		self.mni()

	def shutdown(self):
		self.mni()


class Compute(Object):
	def __init__(self, global_config, config):
		self.global_config = global_config
		self.config = config

	def default_build_dir(self):
		if self.config.build_dir is None:
			raise ValueError("Environment %s does not define a build_dir" % self.config.name)
		return self.config.build_dir

	def spawn(self, config, flavor):
		self.mni()

	@staticmethod
	def factory(name, config):
		print("Create %s compute backend" % name)

		env = config.get_environment(name)
		if env.type == 'local':
			import brcoti_local

			return brcoti_local.compute_factory(config, env)

		if env.type == 'podman':
			import brcoti_podman

			return brcoti_podman.compute_factory(config, env)

		raise NotImplementedError("Compute environment \"%s\" uses type \"%s\" - not implemented" % (name, env.type))

class Config(object):
	class ConfigItem:
		def __init__(self, config, d):
			if d is None:
				d = {}
			for f in self._fields:
				setattr(self, f, d.get(f))

			self._config = config

		def update(self, other):
			for f in self._fields:
				if getattr(self, f) is not None:
					continue
				setattr(self, f, getattr(other, f))

		def __repr__(self):
			return ", ".join(["%s=%s" % (f, getattr(self, f)) for f in self._fields])

	class Globals(ConfigItem):
		_fields = ('output_dir', 'certificates', 'http_proxy')

		def __init__(self, config, d):
			super(Config.Globals, self).__init__(config, d)

	class Engine(ConfigItem):
		_fields = ('name', 'type', 'config')

		def __init__(self, config, d):
			super(Config.Engine, self).__init__(config, d)

		def get_value(self, config_key):
			return self.config.get(config_key)

		def resolve_repository(self, config_key):
			repo_id = self.get_value(config_key)
			if repo_id is None:
				return None

			return self._config.get_repository(self.type, repo_id)

	class Repository(ConfigItem):
		_fields = ('type', 'name', 'url', 'user', 'password', 'credentials', 'repotype')

		def __init__(self, config, d):
			super(Config.Repository, self).__init__(config, d)

		def require_credentials(self):
			if self.user and self.password:
				return

			if self.credentials is None:
				raise ValueError("Authentication required for repository %s/%s, but credentials are incomplete" % (
						self.type, self.name))

			creds = self._config._get_credentials(self.credentials)
			if creds is None:
				raise ValueError("Repository %s/%s references unknown credentials \"%s\"" % (
						self.type, self.name, self.credentials))

			if self.user is None:
				self.user = creds.user
			if self.password is None:
				self.password = creds.password

	class Credential(ConfigItem):
		_fields = ('name', 'user', 'password')

		def __init__(self, config, d):
			super(Config.Credential, self).__init__(config, d)

	class Image(ConfigItem):
		_fields = ('name', 'image')

		def __init__(self, config, d):
			super(Config.Image, self).__init__(config, d)

	class Network(ConfigItem):
		_fields = ('name', 'routing')

		def __init__(self, config, d):
			super(Config.Network, self).__init__(config, d)

	class Pod(ConfigItem):
		_fields = ('name', )

		def __init__(self, config, d):
			super(Config.Pod, self).__init__(config, d)

	class Environment(ConfigItem):
		_fields = ('name', 'type', 'build_dir', 'images', 'network', 'pod')

		def __init__(self, config, d):
			super(Config.Environment, self).__init__(config, d)

			self.images = config._to_list(self.images, Config.Image)
			self.network = config._to_object(self.network, Config.Network)
			self.pod = config._to_object(self.pod, Config.Pod)

		def get_image(self, flavor):
			for img in self.images:
				if img.name == flavor:
					return img

			raise ValueError("Environment \"%s\" does not define an image for \"%s\"" % (self.name, flavor))

	_signature = {
		'globals' : lambda self, o: Config._to_object(self, o, Config.Globals),
		'engines' : lambda self, o: Config._to_list(self, o, Config.Engine),
		'repositories' : lambda self, o: Config._to_list(self, o, Config.Repository),
		'credentials' : lambda self, o: Config._to_list(self, o, Config.Credential),
		'environments' : lambda self, o: Config._to_list(self, o, Config.Environment),
	}

	def __init__(self, cmdline_opts):
		self.command_line_options = cmdline_opts

		self.configs = []

		self.globals = Config.Globals(self, {})
		self.engines = []
		self.credentials = []
		self.repositories = []
		self.environments = []

	def load_file(self, path):
		if not os.path.exists(path):
			return
		with open(path, 'r') as f:
			import json

			d = json.load(f)

			for key, f in self._signature.items():
				raw = d.get(key)
				if raw is None:
					continue

				cooked = f(self, raw)
				if cooked is None:
					continue

				value = getattr(self, key)
				if type(value) == list:
					assert(type(cooked) == list)
					setattr(self, key, value + cooked)
				elif isinstance(value, Config.ConfigItem):
					value.update(cooked)
				else:
					setattr(self, key, cooked)

			self.configs.append(d)

		self._check_list(self.engines, ('name', 'type'))
		self._check_list(self.repositories, ('name', 'type', 'url'))
		self._check_list(self.credentials, ('name', ))

	def get_engine(self, name):
		for e in self.engines:
			if e.name == name:
				return e
		raise ValueError("Unknown build engine \"%s\"" % name)

	def get_environment(self, name):
		for e in self.environments:
			if e.name == name:
				return e
		raise ValueError("Unknown environment \"%s\"" % name)

	def get_repository(self, type, name):
		for r in self.repositories:
			if r.type != type and r.type != 'any':
				continue
			if r.name == name:
				return r
		raise ValueError("No repository named \"%s\" for engine type \"%s\"" % (name, type))

	def _get_credentials(self, name):
		for c in self.credentials:
			if c.name == name:
				return c
		return None

	def get_credentials(self, name):
		creds = self._get_credentials(name)
		if creds is None:
			raise ValueError("No credentials for \"%s\"" % name)
		return creds

	def get_repo_user(self, repo_config):
		user = repo_config.user
		if user is None and repo_config.credentials is not None:
			user = self.get_credentials(repo_config.credentials).user
		return user

	def get_repo_password(self, repo_config):
		password = repo_config.password
		if password is None and repo_config.credentials is not None:
			password = self.get_credentials(repo_config.credentials).password
		return password

	@staticmethod
	def _check_list(l, required_attrs):
		for obj in l:
			for k in required_attrs:
				if getattr(obj, k) is None:
					raise ValueError("%s config lacks required %s attribute" % (type(obj).__name__, k))

	def _to_list(self, json_list, T):
		if json_list is None:
			return

		return [T(self, item) for item in json_list]

	def _to_object(self, json_dict, T):
		return T(self, json_dict)

		result = []
		for item in json_list:
			for f in T._fields:
				if item.get(f) is None:
					item[f] = None

			obj = T(self, item)
			result.append(obj)
		return result

	@staticmethod
	def _to_namedtuple(d, nt):
		return nt(*[d.get(name) for name in nt._fields])

class Engine(Object):
	def __init__(self, name, config, engine_config):
		self.name = engine_config.name

		self.config = config
		self.engine_config = engine_config

		self.state_dir = os.path.join(config.globals.output_dir, engine_config.name)

		opts = config.command_line_options
		self.prefer_git = getattr(opts, "git", False)

		self.index = self.create_index(engine_config)
		self.upstream_index = self.create_upstream_index(engine_config)
		self.downloader = self.create_downloader(engine_config)
		self.uploader = self.create_uploader(engine_config)
		self.publisher = self.create_publisher(engine_config)

	def create_index(self, engine_config):
		repo_config = engine_config.resolve_repository("download-repo")
		if repo_config is None:
			raise ValueError("No download-repo configured for engine \"%s\"" % engine_config.name)

		print("%s: download repo is %s" % (engine_config.name, repo_config.url))

		return self.create_index_from_repo(repo_config)

	def create_upstream_index(self, engine_config):
		repo_config = engine_config.resolve_repository("upstream-repo")
		if repo_config is None:
			raise ValueError("No upstream-repo configured for engine \"%s\"" % engine_config.name)

		print("%s: upstream repo is %s" % (engine_config.name, repo_config.url))

		return self.create_index_from_repo(repo_config)

	def create_publisher(self, engine_config):
		repo_config = engine_config.resolve_repository("publish-repo")
		if repo_config is None:
			raise ValueError("No publish-repo configured for engine \"%s\"" % engine_config.name)

		print("%s: publish repo is %s" % (engine_config.name, repo_config.url))
		return self.create_publisher_from_repo(repo_config)

	def create_downloader(self, engine_config):
		return Downloader()

	def create_uploader(self, engine_config):
		repo_config = engine_config.resolve_repository("upload-repo")
		if repo_config is None:
			print("%s: no upload repo defined" % (engine_config.name))
			return None

		repo_config.require_credentials()

		print("%s: upload repo is %s; user=%s" % (engine_config.name, repo_config.url, repo_config.user))
		return self.create_uploader_from_repo(repo_config)

	def create_binary_download_finder(self, req, verbose = True):
		self.mni()

	def create_source_download_finder(self, req, verbose = True):
		self.mni()

	# Returns a ComputeNode instance
	def prepare_environment(self, compute_backend, build_info):
		compute = compute_backend.spawn(self.engine_config.name)

		if self.config.globals.http_proxy:
			proxy = self.config.globals.http_proxy
			compute.putenv('http_proxy', proxy)
			compute.putenv('https_proxy', proxy)

		return compute

	def downloader(self):
		return Downloader()

	def uploader(self):
		self.mni()

	def create_artefact_from_local_file(self, path):
		self.mni()

	def create_artefact_from_NVT(self, name, version, type):
		self.mni()

	def build_source_locate(self, req, verbose = True):
		finder = self.create_source_download_finder(req, verbose)
		return finder.get_best_match(self.index)

	def build_source_locate_upstream(self, req, verbose = True):
		finder = self.create_source_download_finder(req, verbose)
		return finder.get_best_match(self.upstream_index)

	def build_state_factory(self, sdist):
		savedir = self.build_state_path(sdist.id())
		return BuildState(self, savedir)

	def build_state_path(self, artefact_name):
		return os.path.join(self.state_dir, artefact_name)

	def publish_build_results(self):
		publisher = self.publisher
		if not publisher:
			raise ValueError("%s: no publisher" % self.name)

		publisher.prepare()

		self.rescan_state_dir(publisher)

		publisher.finish()
		publisher.commit()

	def rescan_state_dir(self, publisher):
		print("Scanning %s for artefacts" % self.state_dir);
		for (dir_path, dirnames, filenames) in os.walk(self.state_dir):
			for f in filenames:
				file_path = os.path.join(dir_path, f)
				if publisher.is_artefact(file_path):
					publisher.publish_artefact(file_path)

	def build_unpack(self, compute, sdist):
		self.mni()

	def finalize_build_depdendencies(self, build):
		tempdir = None
		for req in build.build_info.requires:
			missing = []
			for algo in self.REQUIRED_HASHES:
				if req.get_hash(algo) is None:
					missing.append(algo)

			if not missing:
				continue

			# FIXME: the proxy cache should tell us exactly what got downloaded in order
			# to build the package
			print("%s: update missing hash(es): %s" % (req.id(), " ".join(missing)))

			if not tempdir:
				import tempfile

				tempdir = tempfile.TemporaryDirectory(prefix = "build-deps-")

			resolved_req = req.resolution
			if not resolved_req:
				resolved_req = self.resolve_build_requirement(req)
			if not resolved_req:
				raise ValueError("Unable to resolve build dependency %s" % req.name)
			self.downloader.download(resolved_req, tempdir.name)

			for algo in missing:
				resolved_req.update_hash(algo)
				req.add_hash(algo, resolved_req.hash[algo])

		if tempdir:
			tempdir.cleanup()

		return build.build_info.requires

	def create_empty_requirement(self, name):
		self.mni()

	def parse_build_requirement(self, req_string):
		self.mni()

	# Given a build requirement, find the best match in the package index
	def resolve_build_requirement(self, req, verbose = False):
		finder = self.create_binary_download_finder(req, verbose)
		return finder.get_best_match(self.index)

	engine_cache = {}

	@staticmethod
	def factory(name, config, opts):
		engine = Engine.engine_cache.get(name)
		if engine is not None:
			return engine

		print("Create %s builder" % name)
		engine_config = config.get_engine(name)

		print("%s: using %s engine" % (name, engine_config.type))
		if engine_config.type == 'python':
			import brcoti_python

			engine = brcoti_python.engine_factory(config, engine_config)
		elif engine_config.type == 'ruby':
			import brcoti_ruby

			engine = brcoti_ruby.engine_factory(config, engine_config)
		elif engine_config.type == 'rpm':
			import brcoti_rpm

			engine = brcoti_rpm.engine_factory(config, engine_config)
		else:
			raise NotImplementedError("No build engine for \"%s\"" % name)

		Engine.engine_cache[name] = engine
		return engine
