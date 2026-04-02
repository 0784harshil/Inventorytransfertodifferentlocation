-- create_transfer_tables.sql
-- Run this script on BOTH source and destination databases (or just the one hosting history).

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'TransferHeader' AND schema_id = SCHEMA_ID('dbo'))
BEGIN
    CREATE TABLE dbo.TransferHeader (
        TransferID INT IDENTITY(1,1) PRIMARY KEY,
        TransferDate DATETIME DEFAULT GETDATE(),
        SourceLocation NVARCHAR(255) NOT NULL,
        DestinationLocation NVARCHAR(255) NOT NULL,
        CreatedBy NVARCHAR(100) NULL,
        Notes NVARCHAR(MAX) NULL
    );
    PRINT 'Table TransferHeader created.';
END

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'TransferDetail' AND schema_id = SCHEMA_ID('dbo'))
BEGIN
    CREATE TABLE dbo.TransferDetail (
        TransferDetailID INT IDENTITY(1,1) PRIMARY KEY,
        TransferID INT NOT NULL,
        ItemNum NVARCHAR(100) NOT NULL,
        ItemName NVARCHAR(255) NULL,
        Quantity DECIMAL(18, 4) NOT NULL,
        Cost DECIMAL(18, 4) NULL,
        SourceStockBefore DECIMAL(18, 4) NULL,
        SourceStockAfter DECIMAL(18, 4) NULL,
        DestinationStockBefore DECIMAL(18, 4) NULL,
        DestinationStockAfter DECIMAL(18, 4) NULL,
        CONSTRAINT FK_TransferHeader FOREIGN KEY (TransferID) REFERENCES dbo.TransferHeader(TransferID)
    );
    CREATE INDEX IX_TransferDetail_ItemNum ON dbo.TransferDetail(ItemNum);
    PRINT 'Table TransferDetail created.';
END
GO
