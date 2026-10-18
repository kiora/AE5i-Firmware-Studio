# SPDX-License-Identifier: AGPL-3.0-or-later
"""AE5i Firmware Studio - known GEMINI/SW.1.01.15 container profile.

No flashing or network operations. The source container is always the template.
"""
from __future__ import annotations
import csv
import hashlib
import io
import json
import os
import re
import stat
import struct
import tarfile
import tempfile
import zipfile
import zlib
import shutil
import subprocess
from pathlib import Path
from dissect.squashfs import SquashFS

VERSION = '1.4.11'
PROFILE = 'AE5i GEMINI / SW.1.01.15 (fixed slots)'
MAGIC = bytes.fromhex('27051956')
MD5_RE = re.compile(rb'md5sum \$isp_ram_addr (0x[0-9a-fA-F]+) md5sum_value\s+if test "\$md5sum_value" = ([0-9a-fA-F]{32})')
BLOCK_RE = re.compile(rb'^    ispsp set_emmc_blk (\S+) (0x[0-9a-fA-F]+)', re.M)
KNOWN_NAMES = ['uboot2','ecos','kernel','rootfs.','opt.','spsdk.','spapp.','pq','tcon','runtime_cfg','vi','isp_logo','pat_logo','version_info','anm_logo','anm_logo1','anm_logo2','FLASH_DRIVER','GD32_APP']

def digest(data, alg='md5'):
    return hashlib.new(alg, data).hexdigest()

def cstr(b):
    return b.split(b'\0', 1)[0].decode('utf-8', 'replace')

def write_json(path, obj):
    atomic_bytes(path,json.dumps(obj, ensure_ascii=False, indent=2).encode('utf-8'))

def atomic_bytes(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.ae5i-', dir=str(path.parent))
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)

def read_source(path):
    path = Path(path)
    if path.stat().st_size > 512*1024*1024: raise ValueError('输入文件超过 512 MiB 限制。')
    raw = path.read_bytes()
    file_info = dict(path=str(path.resolve()), file_name=path.name, file_size=len(raw), file_md5=digest(raw), file_sha256=digest(raw,'sha256'))
    if zipfile.is_zipfile(io.BytesIO(raw)):
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            members = [x for x in z.infolist() if not x.is_dir() and Path(x.filename).name.upper() == 'GEMINI_PACK.BIN']
            if len(members) != 1:
                raise ValueError('ZIP 必须包含且只包含一个 GEMINI_PACK.BIN。')
            if members[0].file_size > 512*1024*1024:
                raise ValueError('固件超出本配置的 512 MiB 读取限制。')
            data = z.read(members[0])
            file_info['zip_entry'] = members[0].filename
    else:
        data = raw
    return Firmware(data, file_info)

def squash_inventory(data,name,deep=False):
    if data[:4]!=b'hsqs': raise ValueError('该分区不是 SquashFS。')
    try:fs=SquashFS(io.BytesIO(data))
    except Exception as e:raise ValueError('SquashFS 头或压缩参数无效：'+str(e)) from e
    if fs.size>len(data) or fs.size<96 or fs.sb.inodes>100000:
        raise ValueError('SquashFS 长度或 inode 数量异常。')
    rows=[]; seen=set()
    def visit(node,path,depth=0):
        if depth>128 or len(rows)>100000: raise ValueError('文件系统遍历超限。')
        item=dict(path=path,mode=oct(node.mode),uid=node.uid,gid=node.gid,type=stat.S_IFMT(node.mode),
            size=node.size,mtime=node.header.mtime,inode=node.inode_number)
        if node.is_symlink(): item['link']=node.link
        if node.is_device(): item['rdev']=getattr(node.header,'rdev',None)
        if deep and node.is_file():
            h=hashlib.sha256(); total=0
            with node.open() as f:
                while True:
                    block=f.read(1024*1024)
                    if not block:break
                    h.update(block);total+=len(block)
            if total!=node.size:raise ValueError('解压长度错误：'+path)
            item['sha256']=h.hexdigest()
        rows.append(item)
        if node.is_dir():
            key=(node.block,node.offset)
            if key in seen: raise ValueError('文件系统目录循环。')
            seen.add(key)
            for child in node.iterdir():
                if child.name in ['.','..'] or '/' in child.name or '\0' in child.name:
                    raise ValueError('文件系统目录名异常。')
                visit(child,path.rstrip('/')+'/'+child.name,depth+1)
    visit(fs.root,'/')
    xattr=int(fs.sb.xattr_id_table_start)
    result=dict(name=name,compression=int(fs.sb.compression),bytes_used=fs.size,inodes=int(fs.sb.inodes),
        paths=len(rows),entries=sorted(rows,key=lambda x:x['path']),
        xattr_tail_sha256=xattr_digest(data,fs))
    return result

class Firmware:
    def __init__(self, data, file_info=None):
        self.data = bytes(data)
        self.file_info = file_info or {}
        b = self.data
        if len(b)<0x4400 or b[:6]!=b'GEMINI' or b[0x400:0x410]!=b'Gemini_ISP_image':
            raise ValueError('不是受支持的 GEMINI 仪表固件。')
        if struct.unpack_from('<I',b,6)[0] != len(b) or struct.unpack_from('<II',b,0xd8)!=(len(b)-0x400,0x400):
            raise ValueError('外层长度/载荷起点与实际文件不一致；拒绝猜测结构。')
        if cstr(b[0x40:0x80]) != 'SW.1.01.15':
            raise ValueError('当前版本仅支持已验证的 SW.1.01.15 配置；其他版本不进行猜测写入。')
        self.parts=[]
        for pos in range(0xc80,0x1600,0x80):
            name=cstr(b[pos:pos+32])
            off, length, flash, capacity, flags=struct.unpack_from('<5I',b,pos+68)
            off+=0x400
            if off<0x4400 or off+length>len(b) or length>capacity:
                raise ValueError('分区边界或容量无效：'+name)
            payload=b[off:off+length]
            kind='empty' if not length else ('SquashFS' if payload[:4]==b'hsqs' else 'S-record' if name in ['FLASH_DRIVER','GD32_APP'] else 'uImage' if payload[:4]==MAGIC else 'PART' if payload[:4]==b'PART' else 'binary')
            required={'rootfs.':'SquashFS','spsdk.':'SquashFS','spapp.':'SquashFS','uboot2':'uImage','ecos':'uImage','kernel':'uImage','opt.':'empty'}
            if name in required and kind!=required[name]:raise ValueError('分区格式损坏或与当前配置不符：'+name)
            self.parts.append(dict(name=name, table_offset=pos, offset=off, relative_offset=off-0x400, length=length,
                flash_offset=flash, capacity=capacity, import_limit=length, flags=flags, kind=kind,
                md5=digest(payload), stored_md5=cstr(b[pos+32:pos+64]), sha256=digest(payload,'sha256')))
        if [p['name'] for p in self.parts] != KNOWN_NAMES:
            raise ValueError('分区表与已验证的 AE5i 配置不匹配。')
        nonempty=sorted((p['offset'],p['offset']+p['length']) for p in self.parts if p['length'])
        if any(a[1]>c[0] for a,c in zip(nonempty,nonempty[1:])):
            raise ValueError('分区重叠。')
        self.by_name={p['name']:p for p in self.parts}
        self.images=[]
        for off in [0x420]+[p['offset'] for p in self.parts if p['length'] and p['kind']=='uImage']:
            img=self.image(off)
            owner=next((p for p in self.parts if p['offset']==off and p['length']),None)
            if owner and 64+img['size']>owner['length']:raise ValueError('uImage 超出分区载荷：'+owner['name'])
            self.images.append(img)
        init=self.images[0]
        if init['type']!=6 or init['compression']!=0:
            raise ValueError('不支持的初始化升级脚本类型。')
        script=b[0x420+72:0x420+64+init['size']]
        refs=re.findall(rb'isp_image_header_offset \+ (0x[0-9a-fA-F]+)',script)
        if len(refs)!=1:
            raise ValueError('不能唯一定位主升级脚本。')
        mainoff=int(refs[0],16)+0x400
        self.main=self.image(mainoff)
        if self.main['type']!=6 or self.main['compression']!=0 or mainoff<nonempty[-1][1]:
            raise ValueError('主升级脚本与分区重叠或类型不支持。')
        self.images.append(self.main)
        self.script_start=mainoff+72
        self.script_end=mainoff+64+self.main['size']
        self.script=b[self.script_start:self.script_end]
        self.blocks=self.block_records()
        if len(self.blocks)!=74:
            raise ValueError('升级脚本分块数量不是已验证的 74 项；拒绝写入。')
        covered={n:[] for n in KNOWN_NAMES}
        for row in self.blocks:
            p=self.by_name[row['partition']]
            covered[p['name']].append((row['offset']-p['offset'],row['length']))
        for p in self.parts:
            if p['name'] in ['FLASH_DRIVER','GD32_APP']:
                if covered[p['name']]: raise ValueError('MCU 分区脚本格式意外变化。')
                continue
            cursor=0
            for start,n in sorted(covered[p['name']]):
                if start!=cursor:
                    raise ValueError('分块校验未完整连续覆盖分区：'+p['name'])
                cursor+=n
            if cursor!=p['length']:
                raise ValueError('分块长度与分区不一致：'+p['name'])
        loads=re.findall(rb'setexpr isp_update_file_offset \$isp_image_header_offset \+ (0x[0-9a-fA-F]+)[^\n]*\nfatload \$isp_if \$isp_dev \$isp_ram_addr2? \$isp_update_file_name (0x[0-9a-fA-F]+) \$isp_update_file_offset',self.script)
        load_spans=sorted((int(o,16)+0x400,int(n,16)) for o,n in loads)
        expected_spans=sorted([(r['offset'],r['length']) for r in self.blocks]+[(p['offset'],p['length']) for p in self.parts if p['name'] in ['FLASH_DRIVER','GD32_APP']])
        if load_spans!=expected_spans:raise ValueError('脚本读取偏移/长度与分区表不匹配。')
        for img in [self.images[0],self.main]:
            off=img['offset'];size=img['size']
            if struct.unpack_from('>II',self.data,off+64)!=(size-8,0):raise ValueError('脚本 uImage 长度数组不一致。')
        self._inventories={}

    def image(self, off):
        b=self.data
        if off<0 or off+64>len(b) or b[off:off+4]!=MAGIC:
            raise ValueError('uImage 头无效：0x%X'%off)
        h=bytearray(b[off:off+64]); hc=struct.unpack_from('>I',h,4)[0]
        size=struct.unpack_from('>I',h,12)[0]; dc=struct.unpack_from('>I',h,24)[0]
        if off+64+size>len(b):
            raise ValueError('uImage 载荷越界。')
        h[4:8]=bytes(4)
        return dict(offset=off,name=cstr(h[32:]),size=size,type=h[30],compression=h[31],
            header_crc='%08x'%hc,header_crc_actual='%08x'%zlib.crc32(h),data_crc='%08x'%dc,
            data_crc_actual='%08x'%zlib.crc32(b[off+64:off+64+size]), vendor=off==self.by_name['uboot2']['offset'] and h[30]==0x5a)

    def block_records(self):
        out=[]
        for m in MD5_RE.finditer(self.script):
            refs=list(BLOCK_RE.finditer(self.script[:m.start()]))
            if not refs: raise ValueError('分块未找到对应分区。')
            ref=refs[-1]; name=ref[1].decode('ascii')
            if name not in self.by_name: raise ValueError('脚本引用未知分区。')
            p=self.by_name[name]; start=p['offset']+int(ref[2],16)*512; length=int(m[1],16)
            if not length or start<p['offset'] or start+length>p['offset']+p['length']:
                raise ValueError('分块越界：'+name)
            out.append(dict(partition=name,offset=start,length=length,stored_md5=m[2].decode(),
                md5=digest(self.data[start:start+length]),span=m.span(2)))
        return out

    def payload(self,name):
        p=self.by_name[name]
        return self.data[p['offset']:p['offset']+p['length']]

    def inventory(self,name,deep=False):
        if not deep and name in self._inventories:return self._inventories[name]
        result=squash_inventory(self.payload(name),name,deep)
        if not deep:self._inventories[name]=result
        return result

    def verify(self,deep=False):
        checks=[]
        def add(name,ok,detail='',warning=False):
            checks.append(dict(name=name,status='WARN' if warning else 'PASS' if ok else 'FAIL',detail=detail))
        add('外层 MD5',digest(self.data[0x400:])==cstr(self.data[0xea:0x10a]))
        for p in self.parts:add('分区 MD5 / '+p['name'],p['md5']==p['stored_md5'],p['md5'])
        for i,row in enumerate(self.blocks):add('分块 MD5 / %02d / %s'%(i+1,row['partition']),row['md5']==row['stored_md5'])
        for img in self.images:
            name='%s @ 0x%X'%(img['name'],img['offset'])
            if img['vendor']:
                add('厂商 uboot 封装 / '+name,True,'image type=0x5A，原样保留；标准 uImage CRC 不适用，未验证厂商内部算法。',True)
            else:
                add('uImage Header CRC / '+name,img['header_crc']==img['header_crc_actual'])
                add('uImage Data CRC / '+name,img['data_crc']==img['data_crc_actual'])
        fs=[]
        for p in self.parts:
            if p['kind']=='SquashFS':
                try:
                    inv=self.inventory(p['name'],deep)
                    fs.append({k:v for k,v in inv.items() if k!='entries'})
                    add('SquashFS 结构和权限可读 / '+p['name'],True,'%d 条路径；%d 个 inode；未与外部官方基准比对。'%(inv['paths'],inv['inodes']))
                except Exception as e:add('SquashFS / '+p['name'],False,str(e))
            elif p['kind']=='S-record':
                try:
                    _,records,bad=srecords(self.payload(p['name']))
                    add('S-record / '+p['name'],not bad,'%d 行；%d 行校验错误'%(records,bad))
                except Exception as e:add('S-record / '+p['name'],False,str(e))
            elif p['kind']=='PART':
                try:
                    rows=part_archive(self.payload(p['name']))
                    add('PART 目录边界 / '+p['name'],True,'%d 个条目'%len(rows))
                except Exception as e:add('PART / '+p['name'],False,str(e))
        return dict(ok=all(x['status']!='FAIL' for x in checks),checks=checks,filesystems=fs,
            warnings=[x['detail'] for x in checks if x['status']=='WARN'])

    def info(self,deep=False):
        versions=cstr(self.payload('version_info')).strip()
        return dict(tool_version=VERSION,profile=PROFILE,source=self.file_info,bin_size=len(self.data),
            bin_md5=digest(self.data),bin_sha256=digest(self.data,'sha256'),
            outer=dict(magic='GEMINI',software=cstr(self.data[0x40:0x80]),sdk=cstr(self.data[0x80:0xc0]),
                inner_name=cstr(self.data[0xc0:0xd8]),header_size=1024,payload_size=len(self.data)-1024,
                stored_md5=cstr(self.data[0xea:0x10a]),main_script_offset=self.main['offset'],version_info=versions),
            partitions=self.parts,uimages=self.images,verification=self.verify(deep))

    def export(self,directory):
        directory=Path(directory)
        directory.mkdir(parents=True,exist_ok=True)
        # Never overwrite an existing project or source files silently.
        if any(directory.iterdir()): raise ValueError('请选择空文件夹，避免覆盖已有文件。')
        info=self.info()
        for i,p in enumerate(self.parts):
            atomic_bytes(directory/('%02d_%s.bin'%(i,p['name'])),self.payload(p['name']))
        atomic_bytes(directory/'outer_header.bin',self.data[:0x400])
        atomic_bytes(directory/'init_script.uimg',self.data[0x420:0x420+64+self.images[0]['size']])
        atomic_bytes(directory/'main_script.uimg',self.data[self.main['offset']:self.script_end])
        inventories={p['name']:self.inventory(p['name']) for p in self.parts if p['kind']=='SquashFS'}
        write_json(directory/'permissions_manifest.json',inventories)
        write_json(directory/'firmware_info.json',info)
        write_json(directory/'project.json',dict(format='AE5i-fixed-slots-v1',source=self.file_info.get('path'),bin_sha256=digest(self.data,'sha256'),
            partitions=[dict(name=p['name'],file='%02d_%s.bin'%(i,p['name']),length=p['length']) for i,p in enumerate(self.parts)]))
        with (directory/'partitions.csv').open('w',encoding='utf-8-sig',newline='') as f:
            fields=['name','offset','relative_offset','length','flash_offset','capacity','import_limit','kind','md5','sha256']
            w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(self.parts)
        return dict(directory=str(directory),partitions=len(self.parts),manifest='permissions_manifest.json')

    def candidate(self,name,data):
        p=self.by_name[name]
        if len(data)>p['length']:raise ValueError('导入长度 %d 超过原包槽位 %d。闪存容量并非可直接使用的包内空间；本版不重排升级脚本。'%(len(data),p['length']))
        if p['length'] and not data:raise ValueError('不能用空文件替换非空分区。')
        pad=b'\0'
        payload=data+pad*(p['length']-len(data))
        if p['kind']=='SquashFS' and data[:4]!=b'hsqs':raise ValueError('必须导入完整的 SquashFS 镜像。')
        if p['kind']=='uImage' and data[:4]!=MAGIC:raise ValueError('必须导入完整的 uImage 镜像。')
        if p['name']=='uboot2' and payload!=self.payload(name):
            raise ValueError('uboot2 使用厂商封装，内部算法尚未确认；本版只允许原样回填。')
        if p['kind']=='uImage' and payload[28:32]!=self.payload(name)[28:32]:
            raise ValueError('uImage 的 OS/架构/类型/压缩方式与原包不同；本配置不支持此类布局变更。')
        if p['kind']=='S-record':
            payload,_,_=srecords(payload,True)
            if srecord_layout(payload)!=srecord_layout(self.payload(name)):
                raise ValueError('S-record 地址/记录布局变化，无法保证原 MCU 下载长度一致；只允许保持原地址布局的修改。')
        b=bytearray(self.data);b[p['offset']:p['offset']+p['length']]=payload
        candidate=Firmware(b)
        changes=[]
        if p['kind']=='SquashFS':
            old=self.inventory(name);new=candidate.inventory(name,deep=True)
            changes=permission_changes(old,new)
            if changes:raise ValueError('文件清单、Linux 权限/所有者/链接发生变化，已阻止导入。前 12 项：'+json.dumps(changes[:12],ensure_ascii=False))
        elif p['kind']=='PART':part_archive(payload)
        return candidate,payload,dict(name=name,input_size=len(data),slot_size=p['length'],padding=p['length']-len(data),
            input_sha256=digest(data,'sha256'),permission_comparison='PASS' if p['kind']=='SquashFS' else 'N/A')

    def build(self,replacements,output,expected_sha=None):
        if expected_sha and digest(self.data,'sha256')!=expected_sha:raise ValueError('源固件已改变，请重新载入。')
        out=Path(output)
        if self.file_info.get('path') and out.resolve()==Path(self.file_info['path']).resolve():raise ValueError('输出不能覆盖源固件。')
        b=bytearray(self.data);imports=[]
        for name,record in replacements.items():
            if name not in self.by_name:raise ValueError('未知分区：'+name)
            raw=Path(record['path']).read_bytes()
            if digest(raw,'sha256')!=record['sha256']:raise ValueError('暂存导入文件已改变，请重新导入：'+name)
            _,payload,report=self.candidate(name,raw)
            p=self.by_name[name];b[p['offset']:p['offset']+p['length']]=payload;imports.append(report)
        # Repair S-record checksums even when the source itself has bad line checksums.
        for name in ['FLASH_DRIVER','GD32_APP']:
            p=self.by_name[name];fixed,_,_=srecords(bytes(b[p['offset']:p['offset']+p['length']]),True)
            b[p['offset']:p['offset']+p['length']]=fixed
        # Nested image checksums first, followed by partition hashes and script hashes.
        current=Firmware(b)
        for img in current.images:
            if img['vendor']:continue
            off=img['offset'];size=img['size']
            # Update scripts are not editable through the partition import interface.
            struct.pack_into('>I',b,off+24,zlib.crc32(b[off+64:off+64+size]))
            b[off+4:off+8]=bytes(4);struct.pack_into('>I',b,off+4,zlib.crc32(b[off:off+64]))
        for p in self.parts:b[p['table_offset']+32:p['table_offset']+64]=digest(b[p['offset']:p['offset']+p['length']]).encode()
        text=bytearray(self.script)
        for r in self.blocks:text[r['span'][0]:r['span'][1]]=digest(b[r['offset']:r['offset']+r['length']]).encode()
        b[self.script_start:self.script_end]=text
        for img in [self.images[0],self.main]:
            off=img['offset'];struct.pack_into('>I',b,off+24,zlib.crc32(b[off+64:off+64+img['size']]))
            b[off+4:off+8]=bytes(4);struct.pack_into('>I',b,off+4,zlib.crc32(b[off:off+64]))
        b[0xea:0x10a]=digest(b[0x400:]).encode()
        rebuilt=Firmware(b)
        result=rebuilt.info(deep=True)
        if not result['verification']['ok']:raise ValueError('打包后仍有校验失败，未写入输出：'+json.dumps(result['verification'],ensure_ascii=False))
        # Audit every filesystem against the source, including non-imported filesystems.
        for p in self.parts:
            if p['kind']=='SquashFS':
                diffs=permission_changes(self.inventory(p['name']),rebuilt.inventory(p['name']))
                if diffs:raise ValueError('最终文件系统权限不一致：'+p['name'])
        if len(b)!=len(self.data):raise ValueError('包长意外变化。')
        data=bytes(b)
        if out.suffix.lower()=='.zip':
            stream=io.BytesIO()
            with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
                item=zipfile.ZipInfo('GEMINI_PACK.BIN',(2026,10,18,0,0,0));item.compress_type=zipfile.ZIP_DEFLATED;item.external_attr=0o100644<<16;z.writestr(item,data)
            raw=stream.getvalue()
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                if z.read('GEMINI_PACK.BIN')!=data:raise ValueError('ZIP 回读失败。')
        else:raw=data
        atomic_bytes(out,raw)
        # Read back the actual saved bytes before claiming success.
        if digest(out.read_bytes(),'sha256')!=digest(raw,'sha256'):raise ValueError('输出文件回读失败。')
        result.update(output=str(out),output_size=len(raw),output_sha256=digest(raw,'sha256'),source_sha256=digest(self.data,'sha256'),
            byte_identical_to_source=data==self.data,imports=imports,permissions_match_source=True,
            limitation='厂商 uboot 内部算法未验证；uboot 原样保留。权限对比以当前载入文件为基准，不代表官方签名认证。')
        write_json(str(out)+'.report.json',result)
        return result

def permission_changes(old,new):
    def norm(inv):
        groups={}
        for x in inv['entries']:groups.setdefault(x['inode'],[]).append(x['path'])
        return {x['path']:dict(mode=x['mode'],uid=x['uid'],gid=x['gid'],type=x['type'],link=x.get('link'),rdev=x.get('rdev'),
            hardlinks=sorted(groups[x['inode']])) for x in inv['entries']}
    a,b=norm(old),norm(new)
    out=[dict(path=p,before=a.get(p),after=b.get(p)) for p in sorted(a.keys()|b.keys()) if a.get(p)!=b.get(p)]
    if old['xattr_tail_sha256']!=new['xattr_tail_sha256']:out.append(dict(path='[xattrs]',before=old['xattr_tail_sha256'],after=new['xattr_tail_sha256']))
    return out

def srecords(data,repair=False):
    # Reject malformed/truncated lines and non-padding trailing data.
    matches=list(re.finditer(rb'S[0-9][0-9A-Fa-f]+',data));out=bytearray(data);bad=0;last=0;counts=0;seen_end=False
    addr_lengths={0:2,1:2,2:3,3:4,5:2,6:3,7:4,8:3,9:2}
    if not matches:raise ValueError('没有 S-record 记录。')
    for m in matches:
        if data[last:m.start()].strip(b'\r\n\t \0'):raise ValueError('S-record 存在非文本/非填充数据。')
        if seen_end:raise ValueError('结束记录之后仍有数据记录。')
        line=m[0];kind=int(chr(line[1]));raw=bytes.fromhex(line[2:].decode())
        if kind not in addr_lengths or len(raw)!=raw[0]+1 or raw[0]<addr_lengths[kind]+1:raise ValueError('S-record 行长度无效。')
        if kind in [1,2,3]:counts+=1
        if kind in [5,6] and int.from_bytes(raw[1:-1],'big')!=counts:raise ValueError('S-record 记录总数不一致。')
        if kind in [7,8,9]:seen_end=True
        if sum(raw)&255!=255:
            bad+=1
            if repair:out[m.end()-2:m.end()]=('%02X'%((~sum(raw[:-1]))&255)).encode()
        last=m.end()
    if data[last:].strip(b'\r\n\t \0') or not seen_end:raise ValueError('S-record 结尾不完整。')
    return bytes(out),len(matches),bad

def srecord_layout(data):
    sizes={0:2,1:2,2:3,3:4,5:2,6:3,7:4,8:3,9:2}
    out=[]
    for m in re.finditer(rb'S[0-9][0-9A-Fa-f]+',data):
        kind=int(chr(m[0][1]));r=bytes.fromhex(m[0][2:].decode());a=sizes[kind]
        out.append((kind,r[1:1+a].hex(),len(r)-a-2))
    return out

def part_archive(data):
    if data[:4]!=b'PART' or len(data)<16:raise ValueError('PART 头无效。')
    total,header,table=struct.unpack_from('<III',data,4)
    if header!=16 or table%32 or header+table>total or total>len(data):raise ValueError('PART 目录长度无效。')
    out=[]
    for o in range(header,header+table,32):
        name=cstr(data[o:o+24]);size,start=struct.unpack_from('<II',data,o+24)
        if not name or start<header+table or start+size>total:raise ValueError('PART 文件越界：'+name)
        out.append(dict(name=name,offset=start,size=size))
    spans=sorted((r['offset'],r['offset']+r['size']) for r in out if r['size'])
    if any(a[1]>b[0] for a,b in zip(spans,spans[1:])):raise ValueError('PART 条目重叠。')
    return out

WINDOWS_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
WINDOWS_INVALID = set('<>:"/\\|?*')

def xattr_digest(data,fs):
    offset=int(fs.sb.xattr_id_table_start)
    if offset in [-1,0xffffffffffffffff]:return None
    if not 96<=offset<=fs.size-16:raise ValueError('扩展属性表越界。')
    start=struct.unpack_from('<Q',data,offset)[0]
    if not 96<=start<=offset:raise ValueError('扩展属性数据越界。')
    # Include the values before the ID table, not just the ID-table tail.
    return digest(data[start:fs.size],'sha256')


def checked_local_path(path):
    path=Path(os.path.abspath(path))
    for node in [path,*path.parents]:
        try:st=node.lstat()
        except FileNotFoundError:continue
        if stat.S_ISLNK(st.st_mode) or getattr(st,'st_file_attributes',0)&0x400:
            raise ValueError('路径包含符号链接/Windows 重解析点：'+str(node))
    return path


def file_digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()


def validate_windows_tree(entries):
    """Preflight all SquashFS paths before creating any extracted file."""
    seen = {}
    for entry in entries:
        rel = entry['path'].lstrip('/')
        if not rel:
            continue
        pieces = rel.split('/')
        if len(pieces) > 128:
            raise ValueError('SquashFS 目录深度超过 Windows 安全限制：' + rel)
        for part in pieces:
            if (not part or part in ('.', '..') or part[-1] in (' ', '.')
                    or any(ch in WINDOWS_INVALID or ord(ch) < 32 for ch in part)
                    or part.split('.')[0].upper() in WINDOWS_RESERVED):
                raise ValueError('SquashFS 文件名与 Windows 不兼容：' + rel)
        key = rel.casefold()
        old = seen.get(key)
        if old is not None and old != rel:
            raise ValueError('SquashFS 存在 Windows 大小写冲突：' + old + ' / ' + rel)
        seen[key] = rel
    return seen

def extract_squashfs(fw, request):
    """Commit a complete workspace and sidecar; remove partial files on failure."""
    name=request['name']
    if name not in fw.by_name or fw.by_name[name]['kind']!='SquashFS':raise ValueError('只能解包 SquashFS 分区。')
    target=checked_local_path(request['directory'])
    if target.exists() and (not target.is_dir() or any(target.iterdir())):raise ValueError('请选择空目录，避免覆盖已有文件。')
    inv=fw.inventory(name);validate_windows_tree(inv['entries'])
    manifest=target.parent/(target.name+'.ae5i_linux_metadata.json')
    if manifest.exists():raise ValueError('元数据清单已存在：'+str(manifest))
    target.parent.mkdir(parents=True,exist_ok=True)
    data=fw.payload(name);fs=SquashFS(io.BytesIO(data));exported=0;skipped=[]
    was_directory=target.is_dir();committed=False;manifest_committed=False
    try:
        with tempfile.TemporaryDirectory(prefix='.ae5i-extract-',dir=target.parent) as td:
            staging=Path(td)/'files';staging.mkdir()
            def visit(node,parts):
                nonlocal exported
                dest=staging.joinpath(*parts)
                if node.is_dir():
                    dest.mkdir(parents=True,exist_ok=True)
                    for child in node.iterdir():visit(child,parts+[child.name])
                elif node.is_file():
                    with node.open() as src,dest.open('xb') as dst:
                        count=0
                        for block in iter(lambda:src.read(1024*1024),b''):
                            count+=len(block)
                            if count>node.size:raise ValueError('文件长度异常：'+str(dest))
                            dst.write(block)
                        if count!=node.size:raise ValueError('文件读取不完整：'+str(dest))
                    exported+=1
                else:skipped.append('/'+'/'.join(parts))
            visit(fs.root,[])
            meta=dict(format='AE5i-SquashFS-metadata-v1',source_sha256=digest(data,'sha256'),partition=name,
                      inventory=inv,skipped_unix_nodes=skipped,
                      warning='Windows 目录仅包含普通文件和目录；Unix 节点和权限依据原分区清单恢复并复核。')
            staged_meta=Path(td)/'metadata.json';write_json(staged_meta,meta)
            if target.exists():target.rmdir()
            os.replace(staging,target);committed=True
            os.replace(staged_meta,manifest);manifest_committed=True
    except Exception:
        if committed:shutil.rmtree(target)
        if was_directory and not target.exists():target.mkdir()
        if manifest_committed:manifest.unlink()
        raise
    return dict(directory=str(target),files=exported,skipped=len(skipped),metadata=str(manifest))


def workspace_tree(folder):
    out={};stack=[folder]
    while stack:
        base=stack.pop()
        for p in base.iterdir():
            checked_local_path(p)
            mode=p.lstat().st_mode
            if not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):raise ValueError('工作目录中出现特殊节点：'+str(p))
            rel=p.relative_to(folder).as_posix();out[rel]=stat.S_IFMT(mode)
            if stat.S_ISDIR(mode):stack.append(p)
    return out


def ensure_workspace_unchanged(folder,tree,expected_files):
    current=workspace_tree(folder)
    paths=[p for p in sorted(current.keys()|tree.keys()) if current.get(p)!=tree.get(p)]
    if paths:raise ValueError('工作目录清单在构建期间变化：'+', '.join(paths[:8]))
    changed=[p for p,h in expected_files.items() if file_digest(folder/p.lstrip('/'))!=h]
    if changed:raise ValueError('文件内容在构建期间变化：'+', '.join(changed[:8]))


def run_squash_builder(tool,cmd,tarpath):
    with tarpath.open('rb') as stream:
        result=subprocess.run([str(tool),*cmd],stdin=stream,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
            timeout=900,check=False,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if result.returncode:raise ValueError('tar2sqfs 重建失败：'+(result.stderr or result.stdout).decode('utf-8','replace')[-1800:])


def rebuild_squashfs(fw, request):
    """Restore archived Linux metadata when building an edited Windows directory.

    Creates an uncompressed TAR with the source Unix metadata, then feeds it
    into the bundled Windows tar2sqfs binary. The existing candidate() checks
    still decide whether the replacement can be staged.
    """
    name=request['name']
    if name not in fw.by_name or fw.by_name[name]['kind'] != 'SquashFS':
        raise ValueError('只能重建 SquashFS 分区。')
    folder=checked_local_path(request['directory'])
    if not folder.is_dir():raise ValueError('找不到待构建目录。')
    tree=workspace_tree(folder)
    metadata_path=folder.parent/(folder.name+'.ae5i_linux_metadata.json')
    if not metadata_path.is_file():
        raise ValueError('找不到相邻的 .ae5i_linux_metadata.json。请先用本程序解包，以便保存原始 Linux 权限和链接。')
    metadata=json.loads(metadata_path.read_text('utf-8'))
    raw=fw.payload(name)
    if metadata.get('format')!='AE5i-SquashFS-metadata-v1' or metadata.get('partition')!=name or metadata.get('source_sha256')!=digest(raw,'sha256'):
        raise ValueError('Linux 元数据清单与当前固件或分区不匹配，拒绝重建。')
    inventory=fw.inventory(name)
    if metadata.get('inventory')!=inventory:
        raise ValueError('源分区元数据清单不一致。')
    if inventory.get('xattr_tail_sha256') is not None:
        raise ValueError('源 SquashFS 包含扩展属性数据；当前 TAR 路径无法保证 xattr 完整恢复，拒绝重建。')
    tool=Path(__file__).resolve().parent.parent/'tools'/'squashfs-tools-ng'/'tar2sqfs.exe'
    if not tool.is_file():raise ValueError('内置 tar2sqfs.exe 缺失，请完整解压程序压缩包。')
    dest=checked_local_path(request['output'])
    if dest.exists():raise ValueError('目标镜像已存在，请换一个文件名。')
    if dest==Path(request['source']).resolve():raise ValueError('禁止覆盖源固件。')
    if dest.is_relative_to(folder):raise ValueError('输出文件不能放入待重建目录。')
    raw_entries=inventory['entries']
    validate_windows_tree(raw_entries)
    # Windows extraction intentionally writes only directories and regular files.
    # Recreate symlinks, devices and FIFOs directly from the saved Linux metadata.
    known={x['path'].lstrip('/') for x in raw_entries if x['path']!='/' and
           stat.S_IFMT(int(x['mode'],8)) in (stat.S_IFDIR,stat.S_IFREG)}
    skipped={x['path'].lstrip('/') for x in raw_entries if x['path']!='/' and
             stat.S_IFMT(int(x['mode'],8)) not in (stat.S_IFDIR,stat.S_IFREG)}
    actual=set(tree)
    for row in raw_entries:
        rel=row['path'].lstrip('/')
        if rel in known and tree.get(rel)!=row['type']:raise ValueError('工作目录中文件/目录类型变化：'+rel)
    if skipped & actual:
        raise ValueError('Windows 目录中出现应由 Linux 元数据还原的特殊节点：'+', '.join(sorted(skipped & actual)[:8]))
    actual_keys = {}
    for rel in actual:
        key=rel.casefold()
        if key in actual_keys and actual_keys[key]!=rel:
            raise ValueError('Windows 目录存在大小写冲突：'+rel)
        actual_keys[key]=rel
    unexpected=actual-known
    if unexpected:raise ValueError('发现新增文件或目录（必须与源分区清单一致）：'+', '.join(sorted(unexpected)[:8]))
    missing = known-actual
    if missing:raise ValueError('Windows 目录缺少源文件或目录：'+', '.join(sorted(missing)[:8]))
    expected_files={}
    groups={}
    for row in raw_entries:
        if row['type']==stat.S_IFREG:
            rel=row['path'].lstrip('/');h=file_digest(folder/rel)
            expected_files[row['path']]=h
            old=groups.setdefault(row['inode'],h)
            if old!=h:raise ValueError('硬链接的 Windows 副本内容不一致，请同步修改：'+rel)
    original_files={x['path']:x.get('sha256') for x in fw.inventory(name,deep=True)['entries'] if x['type']==stat.S_IFREG}
    if expected_files==original_files:
        ensure_workspace_unchanged(folder,tree,expected_files)
        atomic_bytes(dest,raw)
        return dict(path=str(dest),name=name,sha256=digest(raw,'sha256'),padding=0,permission_comparison='PASS',
                    builder='byte-preserving unchanged workspace',unchanged=True)
    comp=struct.unpack_from('<H',raw,20)[0]
    comp_map={1:'gzip',2:'lzma',3:'lzo',4:'xz',5:'lz4',6:'zstd'}
    if comp not in comp_map:raise ValueError('不支持源文件压缩类型：'+str(comp))
    block=struct.unpack_from('<I',raw,12)[0]
    dest.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.ae5i-sqfs-',dir=dest.parent) as td:
        built=Path(td)/'rebuilt.squashfs'
        tarpath=Path(td)/'archive.tar'
        # Prepare a TAR with the source inode types, ownership, modes, mtime.
        with tarfile.open(tarpath,'w',format=tarfile.PAX_FORMAT) as archive:
            hardlink_roots={}
            for row in raw_entries:
                rel=row['path'].lstrip('/')
                path=folder/rel if rel else folder
                mode=int(row['mode'],8)
                typ=stat.S_IFMT(mode)
                entry=tarfile.TarInfo('./'+rel if rel else './')
                entry.uid=int(row['uid']);entry.gid=int(row['gid'])
                entry.mode=stat.S_IMODE(mode)
                entry.mtime=int(row['mtime'])
                if typ!=stat.S_IFDIR:
                    inode=row['inode']
                    if inode in hardlink_roots:
                        entry.type=tarfile.LNKTYPE;entry.linkname='./'+hardlink_roots[inode];entry.size=0
                        archive.addfile(entry);continue
                    hardlink_roots[inode]=rel
                if typ==stat.S_IFDIR:
                    if not path.is_dir():raise ValueError('目录缺失：'+rel)
                    entry.type=tarfile.DIRTYPE;entry.size=0
                    archive.addfile(entry)
                elif typ==stat.S_IFREG:
                    if not path.is_file():raise ValueError('文件缺失：'+rel)
                    entry.type=tarfile.REGTYPE
                    entry.size=path.stat().st_size
                    with path.open('rb') as stream:archive.addfile(entry,stream)
                elif typ==stat.S_IFLNK:
                    entry.type=tarfile.SYMTYPE
                    entry.linkname=row.get('link','')
                    if not entry.linkname:raise ValueError('软链接目标缺失：'+rel)
                    archive.addfile(entry)
                elif typ in (stat.S_IFCHR,stat.S_IFBLK):
                    rdev=row.get('rdev')
                    if rdev is None:raise ValueError('缺少设备节点编号：'+rel)
                    entry.type=tarfile.CHRTYPE if typ==stat.S_IFCHR else tarfile.BLKTYPE
                    entry.devmajor=(int(rdev)>>8)&0xfff;entry.devminor=(int(rdev)&0xff)|((int(rdev)>>12)&0xfffff00)
                    archive.addfile(entry)
                elif typ==stat.S_IFIFO:
                    entry.type=tarfile.FIFOTYPE;archive.addfile(entry)
                else:
                    raise ValueError('不支持的源节点类型：'+rel)
        cmd=['-s','-j','2','-c',comp_map[comp],'-b',str(block),'-B','1024']
        lzo_parameters=None
        if comp==3:
            options=SquashFS(io.BytesIO(raw))._compression_options
            algorithm,level=struct.unpack('<II',options) if options else (4,8)
            algorithms=['lzo1x_1','lzo1x_1_11','lzo1x_1_12','lzo1x_1_15','lzo1x_999']
            if algorithm>=len(algorithms) or not 1<=level<=9:raise ValueError('源 LZO 压缩参数无效。')
            lzo_parameters=(algorithm,level)
            cmd+=['-X','algorithm='+algorithms[algorithm]+',level='+str(level)]
        cmd+=[str(built)]
        run_squash_builder(tool,cmd,tarpath)
        if not built.is_file():raise ValueError('构建程序未生成输出镜像。')
        data=built.read_bytes()
        newinv=squash_inventory(data,name,deep=True)
        if newinv['compression']!=comp or struct.unpack_from('<I',data,12)[0]!=block:
            raise ValueError('重建镜像压缩类型或块大小与原分区不同。')
        if lzo_parameters is not None:
            options=SquashFS(io.BytesIO(data))._compression_options
            if (struct.unpack('<II',options) if options else (4,8))!=lzo_parameters:raise ValueError('重建镜像未保留原 LZO 算法/等级。')
        before_times={x['path']:x['mtime'] for x in raw_entries}
        after_times={x['path']:x['mtime'] for x in newinv['entries']}
        if before_times!=after_times:raise ValueError('重建镜像未保留原始 Linux 修改时间。')
        actual_files={x['path']:x.get('sha256') for x in newinv['entries'] if x['type']==stat.S_IFREG}
        if actual_files!=expected_files:raise ValueError('重建镜像内容与工作目录不一致，拒绝导入。')
        # Detect edits during TAR creation/packing instead of staging an earlier snapshot.
        ensure_workspace_unchanged(folder,tree,expected_files)
        _,_,report=fw.candidate(name,data)
        if dest.exists():raise ValueError('输出路径在构建期间被占用，未覆盖。')
        atomic_bytes(dest,data)
        return dict(path=str(dest),name=name,sha256=digest(data,'sha256'),padding=report['padding'],
                    permission_comparison='PASS',builder='bundled squashfs-tools-ng 1.1.0',unchanged=False)


def dispatch(request):
    fw=read_source(request['source'])
    expected=request.get('expected_sha256')
    if expected and digest(fw.data,'sha256')!=expected:raise ValueError('源文件已改变，请重新载入。')
    action=request['action']
    if action in ['inspect','verify']:return fw.info(request.get('deep',False))
    if action=='export_all':return fw.export(request['directory'])
    if action=='export_one':
        path=Path(request['output'])
        if path.resolve()==Path(request['source']).resolve():raise ValueError('不能覆盖源固件。')
        atomic_bytes(path,fw.payload(request['name']));return dict(output=str(path))
    if action=='import':
        raw=Path(request['path']).read_bytes();_,_,result=fw.candidate(request['name'],raw)
        result.update(path=request['path'],sha256=digest(raw,'sha256'));return result
    if action=='rebuild_directory':return rebuild_squashfs(fw,request)
    if action=='extract_squashfs':return extract_squashfs(fw,request)
    if action=='import_folder':
        directory=Path(request['directory']);manifest=json.loads((directory/'project.json').read_text('utf-8'))
        if manifest['format']!='AE5i-fixed-slots-v1' or manifest['bin_sha256']!=digest(fw.data,'sha256'):raise ValueError('工程与当前固件不匹配。')
        entries=manifest.get('partitions',[])
        if len(entries)!=len(KNOWN_NAMES) or sorted(p.get('name','') for p in entries)!=sorted(KNOWN_NAMES):raise ValueError('工程必须包含全部 19 个分区，且名称不得重复。')
        for p in entries:
            if p.get('length')!=fw.by_name[p['name']]['length']:raise ValueError('工程槽位长度不匹配：'+p['name'])
        result={}
        for p in entries:
            path=(directory/p['file']).resolve()
            if not path.is_relative_to(directory.resolve()):raise ValueError('工程路径越界。')
            raw=path.read_bytes();fw.candidate(p['name'],raw)
            result[p['name']]=dict(path=str(path),sha256=digest(raw,'sha256'))
        return result
    if action=='build':return fw.build(request.get('replacements',{}),request['output'],expected)
    if action=='permissions':return fw.inventory(request['name'])
    raise ValueError('未知操作：'+action)

def main():
    import sys,traceback
    if len(sys.argv)!=3:raise SystemExit('Usage: firmware.py request.json result.json')
    try:result=dict(success=True,data=dispatch(json.loads(Path(sys.argv[1]).read_text('utf-8-sig'))))
    except Exception as e:result=dict(success=False,error=str(e),traceback=traceback.format_exc())
    write_json(sys.argv[2],result)

if __name__=='__main__':main()
