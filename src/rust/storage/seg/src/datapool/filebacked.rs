// use super::File;
use super::Memory;
use crate::datapool::Datapool;

use std::path::Path;
use std::fs::{File, OpenOptions};
use std::io::prelude::*;
use std::io::{Read, Seek, Write, SeekFrom};

// const HEADER_SIZE: usize = core::mem::size_of::<Header>();

pub struct FileBacked {
    memory: Memory,
    file: File,
    file_size: usize,
}

impl FileBacked {

    pub fn open<T: AsRef<Path>> (
        path:T,
        data_size: usize,
    ) -> Result<Self, std::io::Error> {
        
        
        // Open File
        let mut file = OpenOptions::new()
            .create_new(false)
            .read(true)
            .write(true)
            .open(path)?;

        file.set_len(data_size as u64)?;

        let mut memory = Memory::create(data_size, false);

        file.seek(SeekFrom::Start(0));
        file.read(&mut memory.as_mut_slice());

        let file_size = data_size;

        return Ok(Self {
            memory,
            file,
            file_size,
        });

    }

    pub fn create<T: AsRef<Path>> (
        path: T,
        data_size: usize,
    ) -> Result<Self, std::io::Error> {

        let mut file = OpenOptions::new()
            .create_new(true)
            .read(true)
            .write(true)
            .open(path)?;

        file.set_len(data_size as u64)?;

        let mut memory = Memory::create(data_size, true);

        let file_size = data_size;

        return Ok(Self {
            memory,
            file,
            file_size,
        });
    }

}

impl Datapool for FileBacked {

    fn as_slice(self: &FileBacked) -> &[u8] {
        return self.memory.as_slice();
    }

    fn as_mut_slice(self: &mut FileBacked) -> &mut [u8] {
        return self.memory.as_mut_slice();
    }

    fn flush(self: &mut FileBacked) ->  Result<(), std::io::Error> {
        self.file.seek(SeekFrom::Start(0));
        self.file.write(&self.memory.as_slice());
        return Ok(());
    }

}

#[cfg(test)]
mod filebackedmemory_test {

    use super::*;
    use tempfile::TempDir;

    #[test]
    fn filebackedmemory_datapool() {

        let page_size = 4096;

        let tempdir = TempDir::new().expect("failed to generate tempdir");
        let mut path = tempdir.into_path();
        path.push("filebacked.data");

        let magic_a = [0xDE, 0xCA, 0xFB, 0xAD];
        let magic_b = [0xBA, 0xDC, 0x0F, 0xFE, 0xEB, 0xAD, 0xCA, 0xFE];

        // Create Datapool and Write Data
        {
            let mut datapool = FileBacked::create(&path, 2 * page_size).expect("failed to create pool");
            
            // put data in box (to simulate)
            let mut data = Box::new(datapool);

            assert_eq!(data.len(), 2 * page_size);
            data.flush().expect("failed to flush");

            for (i, byte) in magic_a.iter().enumerate() {
                data.as_mut_slice()[i] = *byte;
            }
            assert_eq!(data.as_slice()[0..4], magic_a[0..4]);
            data.flush().expect("failed to flush");
        }

        // open the datapool and check the content, then update it
        {
            let mut datapool = FileBacked::open(&path, 2 * page_size).expect("failed to open pool");
            
            // put data in box (to simulate)
            let mut data = Box::new(datapool);

            assert_eq!(data.len(), 2 * page_size);
            assert_eq!(data.as_slice()[0..4], magic_a[0..4]);
            assert_eq!(data.as_slice()[4..8], [0; 4]);

            for (i, byte) in magic_b.iter().enumerate() {
                data.as_mut_slice()[i] = *byte;
            }
            data.flush().expect("failed to flush");
        }

        // open the datapool again, and check that it has the new data
        {
            let datapool = FileBacked::open(&path, 2 * page_size).expect("failed to create pool");
            
            // put data in box (to simulate)
            let mut data = Box::new(datapool);

            assert_eq!(data.len(), 2 * page_size);
            assert_eq!(data.as_slice()[0..8], magic_b[0..8]);
        }
    }   
}