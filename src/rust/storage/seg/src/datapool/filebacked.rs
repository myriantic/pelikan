use super::Memory;
use crate::datapool::Datapool;
use blake3::Hash;


use std::path::Path;
use core::ops::Range;
use std::fs::{File, OpenOptions};
use std::io::{Error, ErrorKind, Read, Seek, SeekFrom, Write};
use common::time::{Instant, Nanoseconds, Seconds, UnixInstant};


const PAGE_SIZE: usize = 4096;
const HEADER_SIZE: usize = core::mem::size_of::<Header>();
const MAGIC: [u8; 8] = *b"PELIKAN!";

const VERSION: u64 = 0;

// NOTE: make sure this is a whole number of pages and that all fields which are
// accessed are properly aligned to avoid undefined behavior.
#[repr(packed)]
pub struct Header {
    checksum: [u8; 32],
    magic: [u8; 8],
    version: u64,
    time_monotonic_s: Instant<Seconds<u32>>,
    time_unix_s: UnixInstant<Seconds<u32>>,
    time_monotonic_ns: Instant<Nanoseconds<u64>>,
    time_unix_ns: UnixInstant<Nanoseconds<u64>>,
    user_version: u64,
    options: u64,
    _pad: [u8; 4008],
}

impl Header {
    fn new() -> Self {
        Self {
            checksum: [0; 32],
            magic: MAGIC,
            version: VERSION,
            time_monotonic_s: Instant::<Seconds<u32>>::now(),
            time_unix_s: UnixInstant::<Seconds<u32>>::now(),
            time_monotonic_ns: Instant::<Nanoseconds<u64>>::now(),
            time_unix_ns: UnixInstant::<Nanoseconds<u64>>::now(),
            user_version: 0,
            options: 0,
            _pad: [0; 4008],
        }
    }

    fn as_bytes(&self) -> &[u8] {
        unsafe { std::slice::from_raw_parts((&*self as *const Header) as *const u8, HEADER_SIZE) }
    }

    fn checksum(&self) -> &[u8; 32] {
        &self.checksum
    }

    fn set_checksum(&mut self, hash: Hash) {
        for (idx, byte) in hash.as_bytes()[0..32].iter().enumerate() {
            self.checksum[idx] = *byte;
        }
    }

    fn zero_checksum(&mut self) {
        for byte in self.checksum.iter_mut() {
            *byte = 0;
        }
    }

    fn check(&self) -> Result<(), std::io::Error> {
        self.check_magic()?;
        self.check_version()
    }

    fn check_version(&self) -> Result<(), std::io::Error> {
        if self.version != VERSION {
            Err(Error::new(
                ErrorKind::Other,
                "file has incompatible version",
            ))
        } else {
            Ok(())
        }
    }

    fn check_magic(&self) -> Result<(), std::io::Error> {
        if self.magic[0..8] == MAGIC[0..8] {
            Ok(())
        } else {
            Err(Error::new(ErrorKind::Other, "header is not recognized"))
        }
    }

    fn user_version(&self) -> u64 {
        self.user_version
    }

    fn set_user_version(&mut self, user_version: u64) {
        self.user_version = user_version;
    }

    pub fn options(&self) -> u64 {
        self.options
    }
}

pub struct FileBacked {
    memory: Memory,
    header: Box<[u8]>,
    file: File,
    file_data: Range<usize>,
    user_version: u64,
}

impl FileBacked {
    pub fn open<T: AsRef<Path>>(
        path: T,
        data_size: usize,
        user_version: u64,
    ) -> Result<Self, std::io::Error> {
        // we need the data size to be a whole number of pages for direct io
        let pages = ((HEADER_SIZE + data_size) as f64 / PAGE_SIZE as f64).ceil() as usize;

        // total size must be larger than the requested size to allow for the
        // header
        let file_total_size = Range {
            start: 0,
            end: pages * PAGE_SIZE,
        };

        // data resides after a small header
        let file_data = Range {
            start: HEADER_SIZE,
            end: HEADER_SIZE + data_size,
        };

        // create a new file with read and write access
        // #[cfg(os = "linux")]
        // let mut file = OpenOptions::new()
        //     .create_new(false)
        //     .custom_flags(libc::O_DIRECT)
        //     .read(true)
        //     .write(true)
        //     .open(path)?;

        // #[cfg(not(os = "linux"))]
        let mut file = OpenOptions::new()
            .create_new(false)
            .read(true)
            .write(true)
            .open(path)?;

        // make sure the file size matches the expected size
        if file.metadata()?.len() != file_total_size.end as u64 {
            return Err(Error::new(ErrorKind::Other, "filesize mismatch"));
        }

        // calculate the page range for the data region
        let data_pages = (file_data.end - file_data.start) / PAGE_SIZE;

        // reserve memory for the data
        let mut memory = Memory::create(data_size, true);

        // seek to start of header
        file.seek(SeekFrom::Start(0))?;

        // prepare the header to read from disk
        let mut header = [0; HEADER_SIZE];

        // read the header from disk
        loop {
            if file.read(&mut header[0..PAGE_SIZE])? == PAGE_SIZE {
                break;
            }
            file.seek(SeekFrom::Start(0))?;
        }

        // create a new hasher to checksum the file content, including the
        // header with a zero'd checksum
        let mut hasher = blake3::Hasher::new();

        // turn the raw header into the struct
        let header = unsafe { &mut *(header.as_ptr() as *mut Header) };

        // check the header
        header.check()?;

        // check the user version
        if header.user_version() != user_version {
            return Err(Error::new(ErrorKind::Other, "user version mismatch"));
        }

        // copy the checksum out of the header and zero it in the header
        let file_checksum = header.checksum().to_owned();
        header.zero_checksum();

        // hash the header with the zero'd checksum
        hasher.update(header.as_bytes());

        // seek to start of the data
        file.seek(SeekFrom::Start(file_data.start as u64))?;

        // read the data region from the file, copy it into memory and hash it
        // in a single pass
        for page in 0..data_pages {
            // retry the read until a complete page is read
            loop {
                let start = page * PAGE_SIZE;
                let end = start + PAGE_SIZE;

                if file.read(&mut memory.as_mut_slice()[start..end])? == PAGE_SIZE {
                    hasher.update(&memory.as_slice()[start..end]);
                    break;
                }
                // if the read was incomplete, we seek back to the right spot in
                // the file
                file.seek(SeekFrom::Start((HEADER_SIZE + start) as u64))?;
            }
        }

        // finalize the hash
        let hash = hasher.finalize();

        // compare the checksum agaianst what's in the header
        if file_checksum[0..32] != hash.as_bytes()[0..32] {
            return Err(Error::new(ErrorKind::Other, "checksum mismatch"));
        }

        // return the loaded datapool
        Ok(Self {
            memory,
            header: header.as_bytes().to_owned().into_boxed_slice(),
            file,
            file_data,
            user_version,
        })
    }

    pub fn create<T: AsRef<Path>>(
        path: T,
        data_size: usize,
        user_version: u64,
    ) -> Result<Self, std::io::Error> {
        // we need the data size to be a whole number of pages for direct io
        let pages = ((HEADER_SIZE + data_size) as f64 / PAGE_SIZE as f64).ceil() as usize;

        // total size must be larger than the requested size to allow for the
        // header
        let file_total_size = Range {
            start: 0,
            end: pages * PAGE_SIZE,
        };

        // data resides after a small header
        let file_data = Range {
            start: HEADER_SIZE,
            end: pages * PAGE_SIZE,
        };

        // create a new file with read and write access
        // #[cfg(os = "linux")]
        // let mut file = OpenOptions::new()
        //     .create_new(true)
        //     .custom_flags(libc::O_DIRECT)
        //     .read(true)
        //     .write(true)
        //     .open(path)?;

        // #[cfg(not(os = "linux"))]
        let mut file = OpenOptions::new()
            .create_new(true)
            .read(true)
            .write(true)
            .open(path)?;

        // grow the file to match the total size
        file.set_len(file_total_size.end as u64)?;

        // causes file to be zeroed out
        for page in 0..pages {
            loop {
                if file.write(&[0; PAGE_SIZE])? == PAGE_SIZE {
                    break;
                }
                file.seek(SeekFrom::Start((page * PAGE_SIZE) as u64))?;
            }
        }
        file.sync_all()?;

        let memory = Memory::create(data_size, true);

        Ok(Self {
            memory,
            header: vec![0; HEADER_SIZE].into_boxed_slice(),
            file,
            file_data,
            user_version,
        })
    }

    pub fn determine<T: AsRef<Path> + std::convert::AsRef<std::ffi::OsStr>> (
        path: T,
        data_size: usize,
        user_version: u64, 
    ) -> Result<Self, std::io::Error>  {
        if Path::new(&path).exists(){
            return FileBacked::open(path, data_size, user_version)
        } else {
            return FileBacked::create(path, data_size, user_version)
        };
    }

    pub fn header(&self) -> &Header {
        unsafe { &*(self.header.as_ptr() as *const Header) }
    }

    pub fn time_monotonic_s(&self) -> Instant<Seconds<u32>> {
        self.header().time_monotonic_s
    }

    pub fn time_monotonic_ns(&self) -> Instant<Nanoseconds<u64>> {
        self.header().time_monotonic_ns
    }

    pub fn time_unix_s(&self) -> UnixInstant<Seconds<u32>> {
        self.header().time_unix_s
    }

    pub fn time_unix_ns(&self) -> UnixInstant<Nanoseconds<u64>> {
        self.header().time_unix_ns
    }
}

impl Datapool for FileBacked
 {
    fn as_slice(&self) -> &[u8] {
        self.memory.as_slice()
    }

    fn as_mut_slice(&mut self) -> &mut [u8] {
        self.memory.as_mut_slice()
    }

    fn flush(&mut self) -> Result<(), std::io::Error> {
        // initialize the hasher
        let mut hasher = blake3::Hasher::new();

        // prepare the header
        let mut header = Header::new();

        // set the user version
        header.set_user_version(self.user_version);

        // hash the header with a zero'd checksum
        hasher.update(header.as_bytes());

        // calculate the number of data pages to be copied
        let data_pages = (self.file_data.end - self.file_data.start) / PAGE_SIZE;

        // write the data region to the file and hash it in one pass
        self.file.seek(SeekFrom::Start(HEADER_SIZE as u64))?;
        for page in 0..data_pages {
            loop {
                let start = page * PAGE_SIZE;
                let end = start + PAGE_SIZE;
                if self.file.write(&self.memory.as_slice()[start..end])? == PAGE_SIZE {
                    hasher.update(&self.memory.as_slice()[start..end]);
                    break;
                }
                self.file
                    .seek(SeekFrom::Start((HEADER_SIZE + start) as u64))?;
            }
        }

        // finalize the hash
        let hash = hasher.finalize();

        // set the checksum in the header to the calculated hash
        header.set_checksum(hash);

        // write the header to the file
        self.file.seek(SeekFrom::Start(0))?;
        loop {
            if self.file.write(header.as_bytes())? == HEADER_SIZE {
                break;
            }
            self.file.seek(SeekFrom::Start(0))?;
        }

<<<<<<< HEAD
        self.file.sync_all()?;
=======
        // Create Datapool and Write Data
        {
            let datapool = FileBacked::determine(&path, 2 * page_size).expect("failed to create pool");
            
            // put data in box (to simulate)
            let mut data = Box::new(datapool);
>>>>>>> bb9c7f5dbac963ad8d1ef66486df24080cc569d2

        Ok(())
    }
}

#[test]
fn filebackedmemory_datapool() {
    
    use super::*;
    use tempfile::TempDir;

    let tempdir = TempDir::new().expect("failed to generate tempdir");
    let mut path = tempdir.into_path();
    path.push("mmap_test.data");

    let magic_a = [0xDE, 0xCA, 0xFB, 0xAD];
    let magic_b = [0xBA, 0xDC, 0x0F, 0xFE, 0xEB, 0xAD, 0xCA, 0xFE];

    // create a datapool, write some content to it, and close it
    {
        let mut datapool =
            FileBacked::create(&path, 2 * PAGE_SIZE, 0).expect("failed to create pool");
        assert_eq!(datapool.len(), 2 * PAGE_SIZE);
        datapool.flush().expect("failed to flush");

        for (i, byte) in magic_a.iter().enumerate() {
            datapool.as_mut_slice()[i] = *byte;
        }
        datapool.flush().expect("failed to flush");
    }

    // open the datapool and check the content, then update it
    {
        let mut datapool =
            FileBacked::open(&path, 2 * PAGE_SIZE, 0).expect("failed to open pool");
        assert_eq!(datapool.len(), 2 * PAGE_SIZE);
        assert_eq!(datapool.as_slice()[0..4], magic_a[0..4]);
        assert_eq!(datapool.as_slice()[4..8], [0; 4]);

        for (i, byte) in magic_b.iter().enumerate() {
            datapool.as_mut_slice()[i] = *byte;
        }
        datapool.flush().expect("failed to flush");
    }

    // open the datapool again, and check that it has the new data
    {
        let datapool =
            FileBacked::open(&path, 2 * PAGE_SIZE, 0).expect("failed to create pool");
        assert_eq!(datapool.len(), 2 * PAGE_SIZE);
        assert_eq!(datapool.as_slice()[0..8], magic_b[0..8]);
    }

    // check that the datapool does not open if the user version is incorrect
    {
        assert!(FileBacked::open(&path, 2 * PAGE_SIZE, 1).is_err());
    }
}