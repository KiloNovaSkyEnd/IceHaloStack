"""Regression checks for Windows-safe asynchronous atomic output."""
import tempfile
from pathlib import Path

import numpy as np
import icehalostack as ihs


def main():
    target=Path(tempfile.mkdtemp(prefix='ihs_output_lock_test_'))/'frame_000087.png'
    # Temp names must be unique even for the same destination.
    names={ihs._atomic_temp_path(target).name for _ in range(32)}
    assert len(names)==32 and all(name.endswith('.png') for name in names)

    # Reproduce WinError 32 for the first attempts; the replacement must wait
    # and then finish instead of aborting the whole AsyncOutputPipeline.
    tmp=ihs._atomic_temp_path(target);tmp.write_bytes(b'complete frame')
    real_replace=ihs.os.replace;attempts=[]
    def locked_then_free(src,dst):
        attempts.append((src,dst))
        if len(attempts)<4:
            exc=PermissionError(13,'file is being used by another process',src);exc.winerror=32;raise exc
        return real_replace(src,dst)
    ihs.os.replace=locked_then_free
    try:ihs._atomic_replace_with_retry(tmp,target,timeout=1.0)
    finally:ihs.os.replace=real_replace
    assert len(attempts)==4 and target.read_bytes()==b'complete frame' and not tmp.exists()

    # Exercise the real PNG encoder and final atomic rename too.
    image=np.full((24,32,3),0.25,dtype=np.float32)
    ihs.save_timelapse_sequence_frame_atomic(target,image,'PNG 8-bit','Fast')
    assert target.exists() and target.stat().st_size>32
    leftovers=list(target.parent.glob('*.ihs_tmp.*'))
    assert not leftovers,leftovers
    print('UNIQUE_TEMP_PATH=PASS')
    print('WINERROR32_RETRY=PASS')
    print('ATOMIC_PNG_WRITE=PASS')


if __name__=='__main__':main()
