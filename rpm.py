#
# python specific portions of minibuild
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
import pkginfo
import glob
import shutil
from minibuild.core import ShellCommand

import minibuild.core as core

ENGINE_NAME	= 'rpm'

def canonical_package_name(name):
	return name

class RPMBuildRequirement(core.BuildRequirement):
	engine = ENGINE_NAME

	def __init__(self, name, req_string = None, cooked_requirement = None):
		super(RPMBuildRequirement, self).__init__(canonical_package_name(name), req_string, cooked_requirement)

	class DummyCookedRequirement:
		def __init__(self, req_string):
			self.name = req_string

		def __repr__(self):
			return self.name

	def parse_requirement(self, req_string):
		self.cooked_requirement = self.DummyCookedRequirement(req_string)
		self.req_string = req_string

	@staticmethod
	def from_string(req_string):
		cooked_requirement = RPMBuildRequirement.DummyCookedRequirement(req_string)
		return RPMBuildRequirement(cooked_requirement.name, req_string, cooked_requirement)

	def format(self):
		return str(self.cooked_requirement)

class RPMArtefact(core.Artefact):
	engine = ENGINE_NAME

	def __init__(self, name, version = None, release = None, arch = None):
		super(RPMArtefact, self).__init__(canonical_package_name(name), version)

		self.release = release
		self.arch = arch
		self.filename = None

	@property
	def is_source(self):
		return self.arch in ('src', 'nosrc')

	@staticmethod
	def parse_filename(filename):
		# foo-VER-REL.arch.rpm -> [foo-VER-REL, arch, rpm]
		(stem, arch, suffix) = name.rsplit('.', 2)

		(name, version, release) = stem.rsplit('-', 2)

		return name, version, release, arch

	@staticmethod
	def from_local_file(path, name = None, version = None, release = None, arch = None, type = None):
		filename = os.path.basename(path)

		if not name or not version or not release or not arch:
			# try to detect version and type by looking at the file name
			_name, _version, _release, _arch = RPMArtefact.parse_filename(filename)

			if name:
				assert(name == _name)
			name = _name
			if version:
				assert(version == _version)
			version = _version
			if release:
				assert(release == _release)
			release = _release
			if arch:
				assert(arch == _arch)
			arch = _arch

		build = RPMArtefact(name, version, release, arch)
		build.filename = filename
		build.local_path = path

		for algo in RPMEngine.REQUIRED_HASHES:
			build.update_hash(algo)

		return build

class RPMReleaseInfo(core.PackageReleaseInfo):
	def __init__(self, name, version, parsed_version = None):
		super(RPMReleaseInfo, self).__init__(canonical_package_name(name), version)

	def id(self):
		return "%s-%s" % (self.name, self.version)

	def more_recent_than(self, other):
		assert(isinstance(other, RPMReleaseInfo))
		barf
		return other.parsed_version < this.parsed_version

class RPMPackageInfo(core.PackageInfo):
	def __init__(self, name):
		super(RPMPackageInfo, self).__init__(canonical_package_name(name))

class RPMEngine(core.Engine):
	type = 'rpm'
	REQUIRED_HASHES = ()

	def __init__(self, engine_config):
		super(RPMEngine, self).__init__(engine_config)

		# FIXME: get the name of the pkg manager from engine_config

	def create_empty_requirement(self, name):
		return RPMBuildRequirement(name)

	def parse_build_requirement(self, req_string):
		return RPMBuildRequirement.from_string(req_string)

	def create_artefact_from_local_file(self, path):
		return RPMArtefact.from_local_file(path)

	def create_artefact_from_NVT(self, name, version, type):
		return RPMArtefact(name, version, type)

	def validate_build_requirements(self, requirements, merge_from_upstream = True, recursive = False):
		# For the time being, assume that we can resolve all rpm requirements
		# (they're probably hand crafted anyway)
		return []

	def install_requirement(self, compute, req):
		cmd = ShellCommand("zypper --no-refresh install -y %s" % req, privileged_user = True)
		cmd.no_default_env = True
		compute.exec(cmd)

		# FIXME: return an RPMArtefact representing the package just installed

def engine_factory(engine_config):
	return RPMEngine(engine_config)
