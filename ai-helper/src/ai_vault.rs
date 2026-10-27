// Adapted from PlasmidCraft (MIT); see licenses/PlasmidCraft-AI-MIT.txt.
//! API connections remembered in this application's device-local configuration.
use std::{
    fs,
    io::{Read, Write},
    path::PathBuf,
};
const MAX_CONNECTION_BYTES: u64 = 64 * 1024;
const CLEARED: &[u8] = b"null\n";
pub(crate) trait Vault {
    fn read(&self) -> Result<Option<Vec<u8>>, String>;
    fn write(&self, value: &[u8]) -> Result<(), String>;
    fn delete(&self) -> Result<(), String>;
}
pub(crate) struct DeviceVault {
    path: PathBuf,
    max_bytes: u64,
}
impl DeviceVault {
    pub(crate) fn new(path: PathBuf) -> Self {
        Self::with_limit(path, MAX_CONNECTION_BYTES)
    }
    pub(crate) fn with_limit(path: PathBuf, max_bytes: u64) -> Self {
        Self { path, max_bytes }
    }
    pub(crate) fn read_with_legacy(
        &self,
        legacy: impl FnOnce() -> Option<Vec<u8>>,
    ) -> Result<Option<Vec<u8>>, String> {
        match fs::symlink_metadata(&self.path) {
            Ok(metadata) if !metadata.is_file() || metadata.file_type().is_symlink() => {
                return Err("The saved API connection is not a regular settings file.".into())
            }
            Ok(_) => {
                let file = fs::File::open(&self.path)
                    .map_err(|_| "Could not read the saved API connection.")?;
                let mut bytes = Vec::new();
                file.take(self.max_bytes + 1)
                    .read_to_end(&mut bytes)
                    .map_err(|_| "Could not read the saved API connection.")?;
                if bytes.len() as u64 > self.max_bytes {
                    return Err("The saved API connection is too large.".into());
                }
                return Ok(if bytes == CLEARED { None } else { Some(bytes) });
            }
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
            Err(_) => return Err("Could not read the saved API connection.".into()),
        }
        // Older Mac builds used Keychain. Import only if it can be read without
        // an authentication dialog; never interrupt startup with a password prompt.
        if let Some(bytes) = legacy() {
            self.write(&bytes)?;
            return Ok(Some(bytes));
        }
        Ok(None)
    }
}
impl Vault for DeviceVault {
    fn read(&self) -> Result<Option<Vec<u8>>, String> {
        self.read_with_legacy(legacy_connection)
    }
    fn write(&self, value: &[u8]) -> Result<(), String> {
        if value.len() as u64 > self.max_bytes {
            return Err("The API connection is too large to save.".into());
        }
        let directory = self
            .path
            .parent()
            .ok_or("The app settings folder is unavailable.")?;
        fs::create_dir_all(directory)
            .map_err(|_| "Could not create the app's API settings folder.")?;
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            fs::set_permissions(directory, fs::Permissions::from_mode(0o700))
                .map_err(|_| "Could not prepare the API settings folder.")?;
        }
        if fs::symlink_metadata(&self.path)
            .is_ok_and(|m| !m.is_file() || m.file_type().is_symlink())
        {
            return Err("The API settings destination is not a regular file.".into());
        }
        let mut temporary = tempfile::Builder::new()
            .prefix(".api-connection-")
            .tempfile_in(directory)
            .map_err(|_| "Could not save the API connection on this computer.")?;
        temporary
            .write_all(value)
            .and_then(|_| temporary.as_file().sync_all())
            .map_err(|_| "Could not finish saving the API connection.")?;
        temporary
            .persist(&self.path)
            .map_err(|_| "Could not replace the saved API connection.")?;
        Ok(())
    }
    fn delete(&self) -> Result<(), String> {
        // Clear the credential bytes atomically. This marker also prevents an
        // old Keychain entry from being imported again after an explicit Forget.
        self.write(CLEARED)
    }
}
fn legacy_connection() -> Option<Vec<u8>> {
    None
}

#[cfg(test)]
mod file_tests {
    use super::*;
    fn fixture() -> (tempfile::TempDir, DeviceVault) {
        let directory = tempfile::tempdir().unwrap();
        let vault = DeviceVault::new(directory.path().join("api/connection.json"));
        (directory, vault)
    }
    #[test]
    fn connection_survives_restart_and_is_atomically_replaced() {
        let (_directory, first) = fixture();
        assert!(first.read_with_legacy(|| None).unwrap().is_none());
        first.write(b"synthetic-first-key").unwrap();
        let restarted = DeviceVault::new(first.path.clone());
        assert_eq!(restarted.read().unwrap().unwrap(), b"synthetic-first-key");
        restarted.write(b"synthetic-replacement-key").unwrap();
        assert_eq!(first.read().unwrap().unwrap(), b"synthetic-replacement-key");
        assert_eq!(
            fs::read_dir(first.path.parent().unwrap()).unwrap().count(),
            1
        );
    }
    #[test]
    fn legacy_import_happens_once_and_forget_prevents_resurrection() {
        let (_directory, vault) = fixture();
        assert_eq!(
            vault
                .read_with_legacy(|| Some(b"synthetic-legacy-key".to_vec()))
                .unwrap()
                .unwrap(),
            b"synthetic-legacy-key"
        );
        assert_eq!(
            vault
                .read_with_legacy(|| panic!("legacy must not be queried again"))
                .unwrap()
                .unwrap(),
            b"synthetic-legacy-key"
        );
        vault.delete().unwrap();
        let restarted = DeviceVault::new(vault.path.clone());
        assert!(restarted
            .read_with_legacy(|| panic!("forgotten legacy key must stay forgotten"))
            .unwrap()
            .is_none());
        assert!(!fs::read(&vault.path)
            .unwrap()
            .windows(9)
            .any(|x| x == b"synthetic"));
    }
    #[test]
    fn invalid_destination_and_oversized_writes_preserve_existing_connection() {
        let (_directory, vault) = fixture();
        vault.write(b"synthetic-original-key").unwrap();
        assert!(vault
            .write(&vec![0; MAX_CONNECTION_BYTES as usize + 1])
            .is_err());
        assert_eq!(vault.read().unwrap().unwrap(), b"synthetic-original-key");
        fs::remove_file(&vault.path).unwrap();
        fs::create_dir(&vault.path).unwrap();
        assert!(vault.read().is_err());
        assert!(vault.write(b"synthetic-key").is_err());
    }
    #[cfg(unix)]
    #[test]
    fn local_connection_file_and_folder_have_user_only_permissions() {
        use std::os::unix::fs::PermissionsExt;
        let (_directory, vault) = fixture();
        vault.write(b"synthetic-key").unwrap();
        assert_eq!(
            fs::metadata(&vault.path).unwrap().permissions().mode() & 0o777,
            0o600
        );
        assert_eq!(
            fs::metadata(vault.path.parent().unwrap())
                .unwrap()
                .permissions()
                .mode()
                & 0o777,
            0o700
        );
    }
}
