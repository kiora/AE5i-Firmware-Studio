"""Integration regression suite. No fixture firmware is distributed.

python tests/test_audit.py V11.zip workdir [native-tar2sqfs-for-Linux]
On Windows omit the last argument to run the bundled EXE.
"""
import io,json,sys,stat,struct,tarfile,types,importlib.util
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import firmware as m

def main(source,work,native=None):
    work=Path(work).resolve();work.mkdir(parents=True,exist_ok=True)
    results=[]
    def ok(name,condition=True):
        if not condition:raise AssertionError(name)
        results.append(dict(name=name,passed=True));m.write_json(work/'progress.json',dict(tests=results,count=len(results)));print('PASS',name,flush=True)
    def reject(name,fn):
        try:fn()
        except (ValueError,OSError,KeyError):ok(name);return
        raise AssertionError('Expected rejection: '+name)
    original_runner=m.run_squash_builder
    if native:
        native=Path(native).resolve()
        m.run_squash_builder=lambda tool,cmd,tar:original_runner(native,cmd,tar)
    fw=m.read_source(source)
    info=fw.info(True)
    ok('full source verification and deep decompression',info['verification']['ok'])
    ok('version synchronized',info['tool_version']=='1.4.11')
    ok('19 partitions / 74 script MD5 blocks / 5 image headers',len(fw.parts)==19 and len(fw.blocks)==74 and len(fw.images)==5)
    report=fw.build({},work/'roundtrip.bin')
    ok('unmodified BIN roundtrip is byte-identical',(work/'roundtrip.bin').read_bytes()==fw.data)
    report=fw.build({},work/'roundtrip.zip')
    ok('ZIP output readback and inner CRC',report['verification']['ok'] and report['byte_identical_to_source'])
    # Actual source checksum corruption should be repaired even with no imports.
    data=bytearray(fw.data);p=fw.by_name['GD32_APP'];raw=fw.payload('GD32_APP');line=next(m.re.finditer(rb'S3[0-9A-Fa-f]+',raw));at=p['offset']+line.end()-2
    data[at]=ord('0') if data[at]!=ord('0') else ord('1')
    broken=m.Firmware(data);r=broken.build({},work/'srecord_repair.bin')
    ok('bad source S-record checksum auto repaired without staged import',(work/'srecord_repair.bin').read_bytes()==fw.data)
    reject('oversize import rejected',lambda:fw.candidate('spapp.',fw.payload('spapp.')+b'X'))
    reject('custom uboot modification rejected',lambda:fw.candidate('uboot2',b'X'+fw.payload('uboot2')[1:]))
    reject('source overwrite rejected',lambda:fw.build({},source))
    # Magic corruption cannot evade filesystem checks by becoming a binary partition.
    data=bytearray(fw.data);data[fw.by_name['spapp.']['offset']]=0
    reject('damaged SquashFS signature cannot bypass format validation',lambda:m.Firmware(data))
    # Metadata read can succeed while the data block is corrupt. Import must now fail.
    part=bytearray(fw.payload('spapp.'));fs=m.SquashFS(io.BytesIO(part))
    row=next(x for x in fw.inventory('spapp.')['entries'] if x['type']==stat.S_IFREG and x['size']>100000)
    at=fs.get(row['path']).header.start_block;part[at:at+16]=bytes(16)
    try:
        m.squash_inventory(part,'spapp.')
        readable=True
    except Exception:readable=False
    ok('corrupt-data fixture still has readable metadata',readable)
    reject('corrupt file data rejected by deep import validation',lambda:fw.candidate('spapp.',part))
    # Xattr value storage precedes its ID table, and must be included in the digest.
    fake=types.SimpleNamespace(sb=types.SimpleNamespace(xattr_id_table_start=200),size=256)
    a=bytearray(256);struct.pack_into('<Q',a,200,96);b=bytearray(a);b[120]=1
    ok('xattr values before ID table participate in comparison',m.xattr_digest(a,fake)!=m.xattr_digest(b,fake))
    # Export/import project integrity checks.
    project=work/'project';fw.export(project)
    req=dict(action='import_folder',source=source,directory=str(project))
    manifest=json.loads((project/'project.json').read_text('utf-8'))
    bad=dict(manifest);bad['partitions']=manifest['partitions'][:-1];m.write_json(project/'project.json',bad)
    reject('incomplete project partition list rejected',lambda:m.dispatch(req))
    bad=dict(manifest);bad['partitions']=[manifest['partitions'][0]]*19;m.write_json(project/'project.json',bad)
    reject('duplicate project partition names rejected',lambda:m.dispatch(req))
    m.write_json(project/'project.json',manifest)
    staged=m.dispatch(req)
    ok('complete 19-partition project import',len(staged)==19)
    # Real extraction/rebuild of all three SquashFS partitions, including skipped Unix nodes.
    for name in ['rootfs.','spsdk.','spapp.']:
        directory=work/(name.rstrip('.')+'-files')
        result=m.extract_squashfs(fw,dict(name=name,directory=str(directory)))
        out=work/(name.rstrip('.')+'-unchanged.sqfs')
        r=m.rebuild_squashfs(fw,dict(name=name,directory=str(directory),output=str(out),source=source))
        ok('unchanged workspace preserves raw bytes / '+name,out.read_bytes()==fw.payload(name) and r['unchanged'])
    directory=work/'spapp-files';chosen=next(directory.rglob('*.so'));value=bytearray(chosen.read_bytes());value[-1]^=1;chosen.write_bytes(value)
    out=work/'spapp-edited.sqfs';r=m.rebuild_squashfs(fw,dict(name='spapp.',directory=str(directory),output=str(out),source=source))
    rebuilt,_,_=fw.candidate('spapp.',out.read_bytes())
    original_inv=fw.inventory('spapp.');newinv=rebuilt.inventory('spapp.',True)
    ok('actual edited directory rebuild preserves permissions',not m.permission_changes(original_inv,newinv))
    target='/'+chosen.relative_to(directory).as_posix();entry=next(x for x in newinv['entries'] if x['path']==target)
    ok('edited regular-file content verified inside image',entry['sha256']==m.file_digest(chosen))
    fw.build({'spapp.':dict(path=str(out),sha256=m.digest(out.read_bytes(),'sha256'))},work/'edited_firmware.zip')
    ok('edited SquashFS reintegrated with all firmware checks')
    # An extraction read error must not leave a half-created workspace.
    class FailingNode:
        size=4
        def is_dir(self):return False
        def is_file(self):return True
        def open(self):raise ValueError('injected read failure')
    class FailingRoot:
        def is_dir(self):return True
        def iterdir(self):
            n=FailingNode();n.name='partial';return iter([n])
    real_parser=m.SquashFS;m.SquashFS=lambda stream:types.SimpleNamespace(root=FailingRoot())
    failed=work/'failed-files';failed.mkdir()
    try:reject('extraction failure handled',lambda:m.extract_squashfs(fw,dict(name='spapp.',directory=str(failed))))
    finally:m.SquashFS=real_parser
    ok('failed extraction removes all partial files and sidecar',failed.is_dir() and not list(failed.iterdir()) and not Path(str(failed)+'.ae5i_linux_metadata.json').exists())
    # Create a small genuine filesystem with hardlinks and special nodes.
    tar=work/'special.tar'
    with tarfile.open(tar,'w') as t:
        for name,typ,content,link in [('./',tarfile.DIRTYPE,b'',None),('a',tarfile.REGTYPE,b'original',None),('b',tarfile.LNKTYPE,b'','a'),('sym',tarfile.SYMTYPE,b'','a'),('sym2',tarfile.LNKTYPE,b'','sym'),('pipe',tarfile.FIFOTYPE,b'',None),('dev',tarfile.CHRTYPE,b'',None)]:
            x=tarfile.TarInfo(name);x.type=typ;x.mode=0o755 if typ==tarfile.DIRTYPE else 0o644;x.uid=12;x.gid=34;x.mtime=1234567890;x.size=len(content)
            if link:x.linkname=link
            if typ==tarfile.CHRTYPE:x.devmajor=1;x.devminor=3
            t.addfile(x,io.BytesIO(content) if content else None)
    small=work/'special.sqfs'
    tool=Path(m.__file__).resolve().parent.parent/'tools/squashfs-tools-ng/tar2sqfs.exe'
    m.run_squash_builder(tool,['-s','-j','2','-c','lzo','-b','32768','-B','1024',str(small)],tar)
    data=bytearray(fw.data);p=fw.by_name['spapp.'];raw=small.read_bytes();data[p['offset']:p['offset']+p['length']]=raw+bytes(p['length']-len(raw));smallfw=m.Firmware(data)
    folder=work/'special-files';m.extract_squashfs(smallfw,dict(name='spapp.',directory=str(folder)))
    (folder/'b').write_bytes(b'changed')
    reject('inconsistent hardlink copies rejected instead of losing edit',lambda:m.rebuild_squashfs(smallfw,dict(name='spapp.',directory=str(folder),output=str(work/'links-bad.sqfs'),source=source)))
    (folder/'a').write_bytes(b'changed')
    linked=work/'links-ok.sqfs';r=m.rebuild_squashfs(smallfw,dict(name='spapp.',directory=str(folder),output=str(linked),source=source))
    rebuilt,_,_=smallfw.candidate('spapp.',linked.read_bytes())
    ok('devices FIFO symlinks and symlink-hardlinks restored',not m.permission_changes(smallfw.inventory('spapp.'),rebuilt.inventory('spapp.')))
    if hasattr(Path,'symlink_to'):
        junction=work/'linked-folder'
        try:junction.symlink_to(folder,target_is_directory=True)
        except OSError:pass
        else:reject('linked workspace root rejected before resolve',lambda:m.checked_local_path(junction))
    m.write_json(work/'test_results.json',dict(version=m.VERSION,count=len(results),tests=results,
        firmware_sha256=m.digest(fw.data,'sha256'),builder='squashfs-tools-ng 1.1.0 '+('Linux native build' if native else 'bundled Windows EXE'),
        windows_gui_run=False))
    print('ALL PASSED',len(results),flush=True)

if __name__=='__main__':main(*sys.argv[1:])
